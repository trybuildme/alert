from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api import gibs_proxy
from app.services.tile_service import TileService

router = APIRouter()


def _tile_service(request: Request) -> TileService:
    return request.app.state.tiles


@router.get("/tiles/{product}/{z}/{x}/{y}.png")
async def get_tile(product: str, z: int, x: int, y: int,
                   time: str | None = Query(None, alias="time"),
                   palette: str | None = Query(None),
                   request: Request = None):
    if z < 0 or z > 22:
        raise HTTPException(400, "zoom out of range")
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise HTTPException(404, "tile outside pyramid")
    if product in gibs_proxy.GIBS_PRODUCTS:
        data, source = await gibs_proxy.get_gibs_tile(
            product, z, x, y, time, request.app.state.cache, palette=palette)
        return Response(content=data, media_type="image/png", headers={
            "Cache-Control": "public, max-age=86400",
            "X-Noah-Source": source,
        })
    svc: TileService = _tile_service(request)
    data = await svc.get_tile(product, z, x, y, time)
    if data is None:
        raise HTTPException(404, f"unknown product '{product}'")
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})
