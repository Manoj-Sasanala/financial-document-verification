from fastapi import FastAPI

from app.api.routes.cases import router as cases_router
from app.api.routes.health import router as health_router

app = FastAPI(
    title="AI KYC Document Verification & Risk Copilot",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(cases_router)
