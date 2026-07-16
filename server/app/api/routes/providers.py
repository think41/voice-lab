from fastapi import APIRouter, Response

from app.services import deepgram_catalog, elevenlabs_catalog

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/deepgram/catalog")
async def get_deepgram_catalog() -> dict[str, list[dict]]:
    return await deepgram_catalog.get_catalog()


@router.post("/deepgram/catalog/refresh", status_code=204)
async def refresh_deepgram_catalog() -> Response:
    deepgram_catalog.invalidate_cache()
    return Response(status_code=204)


@router.get("/elevenlabs/catalog")
async def get_elevenlabs_catalog() -> dict[str, list[dict]]:
    return await elevenlabs_catalog.get_catalog()


@router.post("/elevenlabs/catalog/refresh", status_code=204)
async def refresh_elevenlabs_catalog() -> Response:
    elevenlabs_catalog.invalidate_cache()
    return Response(status_code=204)
