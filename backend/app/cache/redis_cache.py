"""
Layered tile cache for ALERT.

Order of operations on get():
    1. In-process LRU memory   (fastest, per-worker)
    2. Redis                   (shared across workers/replicas)
    3. Filesystem              (survives restarts, large capacity)

set() writes through to all available layers. Every layer degrades
gracefully: if Redis is down or the FS is unwritable the service keeps
serving tiles, just slower.
"""

import asyncio
import hashlib
import logging
import os
import time
from collections import OrderedDict

logger = logging.getLogger("alert.cache")

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class MemoryCache:
    def __init__(self, max_items: int = 4096):
        self._store: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._max_items = max_items
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> bytes | None:
        item = self._store.get(key)
        if item is None:
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return item[1]

    def set(self, key: str, value: bytes) -> None:
        self._store[key] = (time.time(), value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_items:
            self._store.popitem(last=False)


class FilesystemCache:
    def __init__(self, root: str, max_age_s: int = 24 * 3600):
        self.root = root
        self.max_age_s = max_age_s
        os.makedirs(root, exist_ok=True)

    def _path(self, key: str) -> str:
        digest = hashlib.sha1(key.encode()).hexdigest()
        return os.path.join(self.root, digest[:2], digest[2:4], digest + ".tile")

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            if time.time() - os.path.getmtime(path) > self.max_age_s:
                return None
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def set(self, key: str, value: bytes) -> None:
        path = self._path(key)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(value)
            os.replace(tmp, path)
        except OSError:
            pass


class RedisCache:
    def __init__(self, url: str):
        self.url = url
        self._client = None
        self._lock = asyncio.Lock()
        self.available = False

    async def _ensure(self):
        if self._client is not None:
            return
        async with self._lock:
            if self._client is not None:
                return
            if not REDIS_AVAILABLE:
                return
            try:
                client = aioredis.from_url(self.url, socket_connect_timeout=0.5, socket_timeout=1.0)
                await client.ping()
                self._client = client
                self.available = True
                logger.info("Redis cache connected at %s", self.url)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); using memory+filesystem only", exc)

    async def get(self, key: str) -> bytes | None:
        await self._ensure()
        if not self.available:
            return None
        try:
            return await self._client.get(f"alert:{key}")
        except Exception:
            self.available = False
            return None

    async def set(self, key: str, value: bytes, ttl: int = 86400) -> None:
        if not self.available:
            return
        try:
            await self._client.setex(f"alert:{key}", ttl, value)
        except Exception:
            self.available = False


class TileCache:
    """Facade combining all cache layers."""

    def __init__(self, redis_url: str | None = None, fs_dir: str | None = None, max_age_s: int = 24 * 3600):
        from app.core.config import settings
        self.memory = MemoryCache()
        self.fs = FilesystemCache(fs_dir or settings.TILE_CACHE_DIR, max_age_s)
        self.redis = RedisCache(redis_url or settings.REDIS_URL)
        self.stats = {"hits": 0, "misses": 0}

    async def get(self, key: str) -> bytes | None:
        val = self.memory.get(key)
        if val is not None:
            self.stats["hits"] += 1
            return val
        val = await self.redis.get(key)
        if val is not None:
            self.memory.set(key, val)
            self.stats["hits"] += 1
            return val
        val = self.fs.get(key)
        if val is not None:
            self.memory.set(key, val)
            self.stats["hits"] += 1
            return val
        self.stats["misses"] += 1
        return None

    async def set(self, key: str, value: bytes, ttl: int = 86400) -> None:
        self.memory.set(key, value)
        await self.redis.set(key, value, ttl)
        self.fs.set(key, value)
