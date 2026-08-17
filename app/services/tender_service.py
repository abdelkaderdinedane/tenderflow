import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks, HTTPException, status

from app.repositories.pipeline_repository import (
    TenderRepository, PipelineRepository, ApprovalRepository
)
from app.services.orchestrator_service import run_pipeline
from app.schemas.pipeline import (
    TenderCreateRequest, TenderCreateResponse,
    PipelineStatusResponse, AgentStatusDetail,
    PipelineResult, ApprovalRequest, ApprovalResponse,
    RunSummary, PipelineStatus, AgentStatus
)
from app.core.logger import get_logger
import json

logger = get_logger("tender_service")

AGENT_ORDER = ["intake", "ocr", "gonogo", "compliance",
               "pricing", "proposal", "tracking"]

def _gen_tender_id() -> str:
    return f"TF-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

def _gen_run_id() -> str:
    return f"RUN-{str(uuid.uuid4())[:8].upper()}"

def _bg_run_pipeline(tender_id: str, run_id: str,
                     raw_text: str, start_from: str = "intake"):
    """Background task — uses its own DB session (Phase 4 fix)."""
    try:
        run_pipeline(tender_id=tender_id, run_id=run_id,
                     raw_text=raw_text, start_from=start_from)
    except Exception as e:
        logger.error(f"Background pipeline crashed: {str(e)}")
        from app.db.session import get_background_db
        from app.repositories.pipeline_repository import PipelineRepository
        with get_background_db() as db:
            repo = PipelineRepository(db)
            repo.update_run_status(run_id, "failed",
                                   error_summary=str(e))

def create_tender_and_start(request: TenderCreateRequest,
                            background_tasks: BackgroundTasks,
                            db: Session) -> TenderCreateResponse:
    tender_id = _gen_tender_id()
    run_id = _gen_run_id()

    tender_repo = TenderRepository(db)
    pipeline_repo = PipelineRepository(db)

    tender_repo.create(tender_id, request.title,
                       request.raw_text, request.source_type.value)
    pipeline_repo.create_run(run_id, tender_id)
    db.commit()

    logger.info(f"Tender created: {tender_id} | Run: {run_id}",
                extra={"event_type": "tender_created"})

    background_tasks.add_task(
        _bg_run_pipeline, tender_id, run_id, request.raw_text
    )

    return TenderCreateResponse(
        tender_id=tender_id,
        pipeline_run_id=run_id,
        status=PipelineStatus.pending,
    )

def get_pipeline_status(tender_id: str,
                        db: Session) -> PipelineStatusResponse:
    repo = PipelineRepository(db)
    run = repo.get_latest_run(tender_id)
    if not run:
        raise HTTPException(status_code=404,
                            detail=f"No pipeline run found for tender {tender_id}")

    agent_runs = repo.get_agent_runs(run.run_id)
    agents = {}
    completed = 0
    for ar in agent_runs:
        agents[ar.agent_name] = AgentStatusDetail(
            status=AgentStatus(ar.status),
            duration_seconds=ar.duration_seconds,
            attempt_number=ar.attempt_number,
            error=ar.error_message,
        )
        if ar.status == "completed":
            completed += 1

    return PipelineStatusResponse(
        tender_id=tender_id,
        run_id=run.run_id,
        pipeline_status=PipelineStatus(run.status),
        current_agent=run.current_agent,
        started_at=run.started_at,
        completed_at=run.completed_at,
        agents=agents,
        agents_completed=completed,
    )

def get_pipeline_result(tender_id: str, db: Session) -> PipelineResult:
    repo = PipelineRepository(db)
    run = repo.get_latest_run(tender_id)
    if not run:
        raise HTTPException(status_code=404,
                            detail=f"No pipeline run found for tender {tender_id}")
    if not run.result_json:
        raise HTTPException(status_code=202,
                            detail="Pipeline still running. No result available yet.")

    result = json.loads(run.result_json)
    agent_runs = repo.get_agent_runs(run.run_id)
    completed = sum(1 for ar in agent_runs if ar.status == "completed")
    total_duration = sum(ar.duration_seconds or 0 for ar in agent_runs)

    return PipelineResult(
        tender_id=tender_id,
        run_id=run.run_id,
        pipeline_status=PipelineStatus(run.status),
        total_duration_seconds=total_duration,
        agents_completed=completed,
        agents_total=7,
        result=result,
    )

def resume_pipeline(tender_id: str, start_from: str,
                    background_tasks: BackgroundTasks,
                    db: Session) -> dict:
    tender_repo = TenderRepository(db)
    tender = tender_repo.get_by_id(tender_id)
    if not tender:
        raise HTTPException(status_code=404,
                            detail=f"Tender {tender_id} not found")

    if start_from not in AGENT_ORDER:
        raise HTTPException(status_code=400,
                            detail=f"Invalid agent name. Must be one of: {AGENT_ORDER}")

    pipeline_repo = PipelineRepository(db)
    run = pipeline_repo.get_latest_run(tender_id)
    if not run:
        raise HTTPException(status_code=404,
                            detail="No pipeline run found to resume")

    pipeline_repo.update_run_status(run.run_id, "in_progress",
                                    error_summary=None)
    db.commit()

    background_tasks.add_task(
        _bg_run_pipeline, tender_id, run.run_id,
        tender.raw_text, start_from
    )
    logger.info(f"Pipeline resuming from {start_from}",
                extra={"event_type": "pipeline_resume"})

    return {"message": f"Pipeline resuming from agent: {start_from}",
            "run_id": run.run_id,
            "tender_id": tender_id}

def submit_approval(tender_id: str, request: ApprovalRequest,
                    db: Session) -> ApprovalResponse:
    pipeline_repo = PipelineRepository(db)
    run = pipeline_repo.get_latest_run(tender_id)
    if not run:
        raise HTTPException(status_code=404,
                            detail=f"No pipeline run found for tender {tender_id}")

    approval_repo = ApprovalRepository(db)
    approval = approval_repo.create(
        tender_id=tender_id,
        run_id=run.run_id,
        decision=request.decision.value,
        reviewer_name=request.reviewer_name,
        comments=request.comments,
    )

    new_status = ("completed_with_approval"
                  if request.decision.value == "approved"
                  else "rejected")
    pipeline_repo.update_run_status(run.run_id, new_status)
    db.commit()

    logger.info(f"Approval submitted: {request.decision.value} by {request.reviewer_name}",
                extra={"event_type": "approval_submitted"})

    return ApprovalResponse(
        tender_id=tender_id,
        pipeline_run_id=run.run_id,
        decision=request.decision,
        reviewer_name=request.reviewer_name,
        comments=request.comments,
        created_at=approval.created_at,
    )

def list_runs(limit: int, db: Session) -> list:
    repo = PipelineRepository(db)
    runs = repo.list_runs(limit)
    result = []
    for run in runs:
        tender_repo = TenderRepository(db)
        tender = tender_repo.get_by_id(run.tender_id)
        agent_runs = repo.get_agent_runs(run.run_id)
        completed = sum(1 for ar in agent_runs if ar.status == "completed")
        result.append(RunSummary(
            run_id=run.run_id,
            tender_id=run.tender_id,
            title=tender.title if tender else None,
            status=PipelineStatus(run.status),
            started_at=run.started_at,
            completed_at=run.completed_at,
            agents_completed=completed,
        ))
    return result
