from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
