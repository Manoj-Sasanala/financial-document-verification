from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.cases import router as cases_router
from app.api.routes.health import router as health_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Load ML/RAG artifacts once; share across requests (QA-07)."""
    from app.startup import load_runtime

    application.state.runtime = load_runtime()
    yield
    application.state.runtime = None


app = FastAPI(
    title="AI KYC Document Verification & Risk Copilot",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(cases_router)
