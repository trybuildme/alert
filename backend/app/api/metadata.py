from fastapi import APIRouter

from app.services.tile_service import PRODUCTS, TileService

router = APIRouter(prefix="/api/products")


@router.get("")
async def list_products():
    items = []
    for pid, meta in PRODUCTS.items():
        m = dict(meta)
        m["id"] = pid
        m["tile_url_template"] = f"/tiles/{pid}/{{z}}/{{x}}/{{y}}.png"
        items.append(m)
    return {"products": items}


@router.get("/{product_id}")
async def product_metadata(product_id: str):
    meta = TileService.product_metadata(product_id)
    if meta is None:
        return {"error": "unknown product"}
    return meta


@router.get("/{product_id}/times")
async def product_times(product_id: str, hours: float = 24.0):
    if product_id not in PRODUCTS:
        return {"error": "unknown product"}
    meta = PRODUCTS[product_id]
    lag = int(meta.get("publication_lag_minutes", 0))
    step = int(meta.get("temporal_step_minutes", 10))
    # Daily products need a wider default window to offer a usable
    # animation range (24h of a daily feed is a single frame).
    span_hours = max(hours, step * 8 / 60.0)
    return {
        "product": product_id,
        "step_minutes": step,
        "publication_lag_minutes": lag,
        "timestamps": TileService.available_times(
            product_id, hours=span_hours, step_min=step, lag_min=lag),
    }
