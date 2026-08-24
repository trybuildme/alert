from fastapi import APIRouter

from app.data.ph_admin import (
    barangays_geojson,
    islands_geojson,
    municipalities_geojson,
    provinces_geojson,
    regions_geojson,
)

router = APIRouter(prefix="/api/admin")


@router.get("/islands")
async def islands():
    return islands_geojson()


@router.get("/regions")
async def regions():
    return regions_geojson()


@router.get("/provinces")
async def provinces(region: str | None = None):
    return provinces_geojson(region)


@router.get("/municipalities")
async def municipalities(province: str | None = None):
    return municipalities_geojson(province)


@router.get("/barangays")
async def barangays(municipality: str | None = None):
    return barangays_geojson(municipality)
