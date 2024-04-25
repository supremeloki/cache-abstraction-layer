import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from cache_layer import (
    CacheError,
    CacheEntry,
    MemoryBackend,
    NullBackend,
    TieredCache,
    key_from_parts,
)


def test_memory_backend_roundtrip():
    cache = MemoryBackend()
    entry = CacheEntry(value="v", stored_at=0.0, ttl_seconds=None)
    cache.put("k", entry)
    assert cache.get("k").value == "v"


def test_ttl_expiry_drops_entry():
    cache = MemoryBackend()
    cache.put("k", CacheEntry(value=1, stored_at=100.0, ttl_seconds=5.0))
    expired = CacheEntry(value=1, stored_at=100.0, ttl_seconds=5.0)
    assert not expired.is_expired(now=104.9)
    assert expired.is_expired(now=105.1)
    fake_now = 200.0
    stale = CacheEntry(value=1, stored_at=100.0, ttl_seconds=5.0)
    assert stale.is_expired(now=fake_now)


def test_lru_eviction_order():
    cache = MemoryBackend(max_items=2)
    for i in range(3):
        cache.put(f"k{i}", CacheEntry(value=i, stored_at=0.0, ttl_seconds=None))
    assert cache.get("k0") is None
    assert cache.get("k1") is not None
    assert cache.stats().evictions == 1


def test_lru_touch_prevents_eviction():
    cache = MemoryBackend(max_items=2)
    cache.put("a", CacheEntry(value=1, stored_at=0.0, ttl_seconds=None))
    cache.put("b", CacheEntry(value=2, stored_at=0.0, ttl_seconds=None))
    cache.get("a")
    cache.put("c", CacheEntry(value=3, stored_at=0.0, ttl_seconds=None))
    assert cache.get("a") is not None
    assert cache.get("b") is None


def test_stats_hit_ratio():
    cache = MemoryBackend()
    cache.put("hit", CacheEntry(value=1, stored_at=0.0, ttl_seconds=None))
    cache.get("hit")
    cache.get("miss")
    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.hit_ratio == pytest.approx(0.5)


def test_null_backend_always_misses():
    null = NullBackend()
    null.put("x", CacheEntry(value=1, stored_at=0.0, ttl_seconds=None))
    assert null.get("x") is None
    assert null.size() == 0


def test_invalid_max_items_rejected():
    with pytest.raises(CacheError):
        MemoryBackend(max_items=0)


def test_tiered_requires_backend():
    with pytest.raises(CacheError):
        TieredCache([])


def test_tiered_promotes_from_slow_to_fast():
    fast, slow = NullBackend(), MemoryBackend()
    tiered = TieredCache([fast, slow], default_ttl=None)
    tiered.put("key", "value")
    slow_only = slow.get("key")
    assert slow_only is not None
    promoted = tiered.get("key")
    assert promoted == "value"


def test_tiered_delete_clears_all_levels():
    l1, l2 = MemoryBackend(), MemoryBackend()
    tiered = TieredCache([l1, l2], default_ttl=None)
    tiered.put("k", 7)
    assert tiered.delete("k") == 2
    assert tiered.get("k") is None


def test_cached_decorator_roundtrip():
    tiered = TieredCache([MemoryBackend()], default_ttl=None)
    calls = {"n": 0}

    @tiered.cached(lambda x: key_from_parts("square", x))
    def square(x: int) -> int:
        calls["n"] += 1
        return x * x

    assert square(4) == 16
    assert square(4) == 16
    assert calls["n"] == 1
