# cache-abstraction-layer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tiered caching abstraction with pluggable backends, TTL entries, LRU eviction, hit-ratio stats, and a decorator API — swap Redis for memory without touching call sites.

## 🚀 Overview

Cache logic leaks everywhere when it's hand-rolled: expiry math in one file, eviction in another, stats nowhere. `cache-abstraction-layer` centralizes it: backends implement a four-method `Protocol` (`get/put/delete/clear`), entries carry their own TTL as frozen dataclasses, and a `TieredCache` chains backends (L1 hot → L2 cold) with automatic promotion of hits from slower tiers.

## ✨ Features

- **Backend Protocol:** structural typing — any object with get/put/delete/size/clear plugs in; no inheritance
- **MemoryBackend:** LRU-ordered with bounded capacity and lazy TTL expiry on read
- **NullBackend:** always-miss sink for disabling cache in tests/dev with zero code changes
- **Frozen CacheEntry:** value + stored_at + ttl; expiration is a pure predicate
- **TieredCache:** multi-level lookup, cross-level promotion, delete-all-levels semantics
- **Stats everywhere:** hits / misses / evictions / size + computed `hit_ratio`
- **Decorator API:** `@tiered.cached(lambda x: key(x))` memoizes any function
- **Zero dependencies**

## 🚧 Structure

```
cache-abstraction-layer/
├── src/cache_layer/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── README.md
└── pyproject.toml
```

## 📦 Installation

```bash
git clone https://github.com/supremeloki/cache-abstraction-layer.git
cd cache-abstraction-layer
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 🏃 Quick Start

```python
from cache_layer import MemoryBackend, TieredCache, key_from_parts

tiered = TieredCache(
    backends=[MemoryBackend(max_items=512), MemoryBackend(max_items=8192)],
    default_ttl=60.0,
)

tiered.put("user:42", {"name": "Sara"})
user = tiered.get("user:42")
```

### Memoization decorator

```python
@tiered.cached(lambda query: key_from_parts("search", query), ttl_seconds=30)
def expensive_search(query: str) -> list[str]:
    ...
```

## 🔧 Error Handling

```text
CacheError
├── BackendUnavailableError   # reserved for IO-backed backends
└── SerializationError        # reserved for encoded stores
```

Expiry never raises — stale entries behave as misses.

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📝 Code Quality

- Full type hints (`X | None` style), generic `CacheEntry[T]`, frozen contracts
- Zero comments — names carry the meaning
- `ruff` clean

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👤 Author

**Kooroush Masoumi**

---

⭐ Star this repo if you find it useful!
