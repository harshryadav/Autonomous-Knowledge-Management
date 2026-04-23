"""In-memory caching helpers used by the demo service."""


_store: dict = {}


def get(key):
    """Return the cached value for `key`, or None if it's not cached."""
    # Caching reads avoids hitting the (hypothetical) slow backend.
    return _store.get(key)


def put(key, value):
    """Store `value` under `key` for future lookups."""
    # Writes are intentionally overwrite-on-conflict to keep the API simple.
    _store[key] = value


def clear():
    """Drop every entry. Useful for tests and cold-start scenarios."""
    _store.clear()
