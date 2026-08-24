from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    cache = getattr(request.app.state, "cache", None)
    return {
        "status": "ok",
        "service": "AURORA-GIS",
        "version": "1.0.0",
        "cache": {
            "memory_items": len(cache.memory._store) if cache else 0,
            "memory_hits": cache.memory.hits if cache else 0,
            "redis_available": bool(cache and cache.redis.available),
            "total_hits": cache.stats["hits"] if cache else 0,
            "total_misses": cache.stats["misses"] if cache else 0,
        },
    }
