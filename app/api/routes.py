from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from datetime import datetime
import requests

from app.db.session import get_db
from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.pipeline import (
    TenderCreateRequest, TenderCreateResponse,
    PipelineStatusResponse, PipelineResult,
    PipelineResumeRequest, ApprovalRequest, ApprovalResponse,
    RunSummary, HealthResponse
)
from app.services import tender_service

# ── Tenders ──
tenders_router = APIRouter(
    prefix="/api/v1/tenders",
    tags=["Tenders"],
)

@tenders_router.post(
    "",
    response_model=TenderCreateResponse,
    status_code=201,
    summary="Submit a new tender",
    description="Creates a new tender record and automatically starts the 7-agent pipeline."
)
def create_tender(
    request: TenderCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.create_tender_and_start(request, background_tasks, db)

# ── Pipeline ──
pipeline_router = APIRouter(
    prefix="/api/v1/pipeline",
    tags=["Pipeline"],
)

@pipeline_router.get(
    "/{tender_id}/status",
    response_model=PipelineStatusResponse,
    summary="Get pipeline execution status",
)
def get_status(
    tender_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.get_pipeline_status(tender_id, db)

@pipeline_router.get(
    "/{tender_id}/result",
    response_model=PipelineResult,
    summary="Get consolidated pipeline result",
)
def get_result(
    tender_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.get_pipeline_result(tender_id, db)

@pipeline_router.post(
    "/{tender_id}/resume",
    summary="Resume pipeline from a specific agent",
)
def resume(
    tender_id: str,
    request: PipelineResumeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.resume_pipeline(
        tender_id, request.start_from, background_tasks, db
    )

# ── Approvals ──
approvals_router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["Approvals"],
)

@approvals_router.post(
    "/{tender_id}",
    response_model=ApprovalResponse,
    summary="Submit approval or rejection decision",
)
def approve(
    tender_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.submit_approval(tender_id, request, db)

# ── Runs ──
runs_router = APIRouter(
    prefix="/api/v1/runs",
    tags=["Runs"],
)

@runs_router.get(
    "",
    response_model=list[RunSummary],
    summary="List recent pipeline runs",
)
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return tender_service.list_runs(limit, db)

# ── Health ──
health_router = APIRouter(
    prefix="/api/v1/health",
    tags=["Health"],
)

@health_router.get(
    "",
    response_model=HealthResponse,
    summary="Health check — no auth required",
)
def health(db: Session = Depends(get_db)):
    # Check DB
    db_status = "healthy"
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    # Check Ollama
    ollama_status = "healthy"
    try:
        r = requests.get(f"{settings.OLLAMA_BASE_URL}", timeout=3)
        if r.status_code != 200:
            ollama_status = "unhealthy"
    except Exception:
        ollama_status = "unreachable"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow().isoformat() + "Z",
        database=db_status,
        ollama=ollama_status,
    )
