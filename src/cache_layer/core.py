from __future__ import annotations

import time
from abc import abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Generic, Protocol, TypeVar

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class CacheError(Exception):
    pass


class BackendUnavailableError(CacheError):
    pass


class SerializationError(CacheError):
    pass


@dataclass(frozen=True)
class CacheEntry(Generic[ValueT]):
    value: ValueT
    stored_at: float
    ttl_seconds: float | None

    def is_expired(self, now: float | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        reference = now if now is not None else time.monotonic()
        return (reference - self.stored_at) >= self.ttl_seconds


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    evictions: int
    size: int

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class StatsTracker:
    def __init__(self) -> None:
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def record_hit(self) -> None:
        self._hits += 1

    def record_miss(self) -> None:
        self._misses += 1

    def record_eviction(self) -> None:
        self._evictions += 1

    def snapshot(self, size: int) -> CacheStats:
        return CacheStats(hits=self._hits, misses=self._misses,
                          evictions=self._evictions, size=size)


class Backend(Protocol):
    def get(self, key: str) -> CacheEntry[Any] | None: ...
    def put(self, key: str, entry: CacheEntry[Any]) -> None: ...
    def delete(self, key: str) -> bool: ...
    def clear(self) -> int: ...
    def size(self) -> int: ...


class MemoryBackend:
    def __init__(self, max_items: int = 256) -> None:
        if max_items < 1:
            raise CacheError("max_items must be positive")
        self._store: OrderedDict[str, CacheEntry[Any]] = OrderedDict()
        self._max_items = max_items
        self._stats = StatsTracker()

    def get(self, key: str) -> CacheEntry[Any] | None:
        entry = self._store.get(key)
        if entry is None:
            self._stats.record_miss()
            return None
        if entry.is_expired():
            del self._store[key]
            self._stats.record_miss()
            return None
        self._store.move_to_end(key)
        self._stats.record_hit()
        return entry

    def put(self, key: str, entry: CacheEntry[Any]) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = entry
        while len(self._store) > self._max_items:
            _, evicted = self._store.popitem(last=False)
            self._stats.record_eviction()

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> int:
        removed = len(self._store)
        self._store.clear()
        return removed

    def size(self) -> int:
        return len(self._store)

    def stats(self) -> CacheStats:
        return self._stats.snapshot(len(self._store))


class NullBackend:
    def __init__(self) -> None:
        self._stats = StatsTracker()

    def get(self, key: str) -> CacheEntry[Any] | None:
        self._stats.record_miss()
        return None

    def put(self, key: str, entry: CacheEntry[Any]) -> None: ...
    def delete(self, key: str) -> bool:
        return False

    def clear(self) -> int:
        return 0

    def size(self) -> int:
        return 0

    def stats(self) -> CacheStats:
        return self._stats.snapshot(0)


class TieredCache:
    def __init__(self, backends: list[Backend], default_ttl: float | None = 60.0) -> None:
        if not backends:
            raise CacheError("at least one backend required")
        self._backends = backends
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        for level, backend in enumerate(self._backends):
            entry = backend.get(key)
            if entry is not None and not entry.is_expired():
                if level > 0:
                    self._promote(key, entry, level)
                return entry.value
            if entry is not None:
                backend.delete(key)
        return None

    def put(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        effective_ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        entry: CacheEntry[Any] = CacheEntry(
            value=value, stored_at=time.monotonic(), ttl_seconds=effective_ttl
        )
        for backend in self._backends:
            backend.put(key, entry)

    def delete(self, key: str) -> int:
        return sum(1 for backend in self._backends if backend.delete(key))

    def clear(self) -> int:
        return sum(backend.clear() for backend in self._backends)

    def _promote(self, key: str, entry: CacheEntry[Any], found_level: int) -> None:
        for backend in self._backends[:found_level]:
            backend.put(key, entry)

    def cached(self, key_builder: Callable[..., str], ttl_seconds: float | None = None):
        def decorator(func: Callable[..., ValueT]) -> Callable[..., ValueT]:
            def wrapper(*args: Any, **kwargs: Any) -> ValueT:
                cache_key = key_builder(*args, **kwargs)
                hit = self.get(cache_key)
                if hit is not None:
                    return hit
                result = func(*args, **kwargs)
                self.put(cache_key, result, ttl_seconds=ttl_seconds)
                return result

            return wrapper

        return decorator


def key_from_parts(*parts: Any) -> str:
    return "|".join(str(part) for part in parts)
