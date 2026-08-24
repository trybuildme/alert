import os


class Settings:
    APP_NAME: str = "NOAH"
    VERSION: str = "1.0.0"

    # Redis (optional at dev time; falls back to filesystem + memory)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6380/0")

    # Filesystem tile cache
    TILE_CACHE_DIR: str = os.getenv("NOAH_TILE_CACHE_DIR", "/tmp/noah-tilecache")
    FS_CACHE_MAX_AGE_S: int = int(os.getenv("NOAH_FS_CACHE_MAX_AGE", str(24 * 3600)))

    # Tile rendering
    TILE_SIZE: int = 256

    # CORS
    CORS_ORIGINS: list = ["*"]

    # --- Earthquake intelligence module (docs/earthquake/) ---
    EARTHQUAKE_ENABLED: bool = os.getenv("EARTHQUAKE_ENABLED", "1") == "1"
    EARTHQUAKE_POLL_INTERVAL: int = int(os.getenv("EARTHQUAKE_POLL_INTERVAL", "300"))
    EARTHQUAKE_MIN_MAGNITUDE: float = float(os.getenv("EARTHQUAKE_MIN_MAGNITUDE", "2.5"))
    # Ingestion lookback window in minutes (overlaps slightly to be safe)
    EARTHQUAKE_LOOKBACK_MINUTES: int = int(os.getenv("EARTHQUAKE_LOOKBACK_MINUTES", "180"))
    # One-time history backfill at startup (days); 0 disables
    EARTHQUAKE_BACKFILL_DAYS: int = int(os.getenv("EARTHQUAKE_BACKFILL_DAYS", "30"))
    # Map/API default query window in days
    EARTHQUAKE_HISTORY_DAYS: int = int(os.getenv("EARTHQUAKE_HISTORY_DAYS", "30"))
    EARTHQUAKE_MAX_DEPTH_KM: float = float(os.getenv("EARTHQUAKE_MAX_DEPTH_KM", "800"))
    EARTHQUAKE_DB_PATH: str = os.getenv("NOAH_EQ_DB",
                                        os.path.join(os.path.dirname(__file__),
                                                     "..", "..", "data", "earthquakes.db"))
    # USGS bounding box, order: minlon,minlat,maxlon,maxlat
    # (default: Philippines region). Empty string = global feed.
    EARTHQUAKE_BBOX: str = os.getenv("EARTHQUAKE_BBOX", "115,4,127,21")
    EARTHQUAKE_ALERT_ENABLED: bool = os.getenv("EARTHQUAKE_ALERT_ENABLED", "1") == "1"
    EARTHQUAKE_ALERT_RULES_PATH: str = os.getenv("NOAH_EQ_ALERT_RULES", "")
    EARTHQUAKE_WS_ENABLED: bool = os.getenv("EARTHQUAKE_WS_ENABLED", "1") == "1"
    # Regional monitoring focus (default: Aurora Province, PH)
    NOAH_EQ_REF_LAT: float = float(os.getenv("NOAH_EQ_REF_LAT", "15.78"))
    NOAH_EQ_REF_LON: float = float(os.getenv("NOAH_EQ_REF_LON", "121.55"))
    NOAH_EQ_REF_RADIUS_KM: float = float(os.getenv("NOAH_EQ_REF_RADIUS_KM", "150"))


settings = Settings()
