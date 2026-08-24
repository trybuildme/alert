import os


class Settings:
    APP_NAME: str = "AURORA-GIS"
    VERSION: str = "1.0.0"

    # Redis (optional at dev time; falls back to filesystem + memory)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6380/0")

    # Filesystem tile cache
    TILE_CACHE_DIR: str = os.getenv("AURORA_TILE_CACHE_DIR", "/tmp/aurora-tilecache")
    FS_CACHE_MAX_AGE_S: int = int(os.getenv("AURORA_FS_CACHE_MAX_AGE", str(24 * 3600)))

    # Tile rendering
    TILE_SIZE: int = 256

    # CORS
    CORS_ORIGINS: list = ["*"]


settings = Settings()
