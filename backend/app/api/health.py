from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe. Intentionally has no DB or AWS dependency so it stays
    cheap and side-effect free."""
    return {"status": "ok"}
