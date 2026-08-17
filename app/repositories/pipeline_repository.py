from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, List
from app.db.models import Tender, PipelineRun, AgentRun, Approval
from app.core.logger import get_logger

logger = get_logger("repository")

AGENT_ORDER = ["intake", "ocr", "gonogo", "compliance",
               "pricing", "proposal", "tracking"]

class TenderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, tender_id: str, title: str,
               raw_text: str, source_type: str) -> Tender:
        tender = Tender(
            tender_id=tender_id,
            title=title,
            raw_text=raw_text,
            source_type=source_type,
        )
        self.db.add(tender)
        self.db.flush()
        return tender

    def get_by_id(self, tender_id: str) -> Optional[Tender]:
        return self.db.query(Tender).filter_by(tender_id=tender_id).first()

    def exists(self, tender_id: str) -> bool:
        return self.db.query(Tender).filter_by(
            tender_id=tender_id).count() > 0

class PipelineRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, run_id: str, tender_id: str) -> PipelineRun:
        run = PipelineRun(
            run_id=run_id,
            tender_id=tender_id,
            status="pending",
            started_at=datetime.utcnow(),
        )
        self.db.add(run)
        for agent in AGENT_ORDER:
            self.db.add(AgentRun(
                pipeline_run_id=run_id,
                agent_name=agent,
                status="pending",
            ))
        self.db.flush()
        return run

    def get_latest_run(self, tender_id: str) -> Optional[PipelineRun]:
        return (self.db.query(PipelineRun)
                .filter_by(tender_id=tender_id)
                .order_by(PipelineRun.started_at.desc())
                .first())

    def get_run_by_id(self, run_id: str) -> Optional[PipelineRun]:
        return self.db.query(PipelineRun).filter_by(run_id=run_id).first()

    def update_run_status(self, run_id: str, status: str,
                          current_agent: str = None,
                          error_summary: str = None,
                          result_json: str = None):
        run = self.db.query(PipelineRun).filter_by(run_id=run_id).first()
        if not run:
            return
        run.status = status
        if current_agent is not None:
            run.current_agent = current_agent
        if error_summary is not None:
            run.error_summary = error_summary
        if result_json is not None:
            run.result_json = result_json
        if status in ["completed", "completed_with_approval",
                      "failed", "partial", "waiting_approval",
                      "no_go", "rejected"]:
            run.completed_at = datetime.utcnow()
        self.db.flush()

    def upsert_agent_run(self, run_id: str, agent_name: str,
                         status: str, response: str = None,
                         duration: float = None, error: str = None,
                         attempt: int = 1):
        agent_run = (self.db.query(AgentRun)
                     .filter_by(pipeline_run_id=run_id,
                                agent_name=agent_name)
                     .first())
        if not agent_run:
            agent_run = AgentRun(
                pipeline_run_id=run_id,
                agent_name=agent_name,
            )
            self.db.add(agent_run)

        agent_run.status = status
        agent_run.attempt_number = attempt

        if status == "running":
            agent_run.started_at = datetime.utcnow()
        elif status in ["completed", "failed"]:
            agent_run.completed_at = datetime.utcnow()
            agent_run.raw_response = response
            agent_run.duration_seconds = duration
            agent_run.error_message = error
            agent_run.validation_success = error is None

        self.db.flush()

    def get_agent_runs(self, run_id: str) -> List[AgentRun]:
        return (self.db.query(AgentRun)
                .filter_by(pipeline_run_id=run_id)
                .all())

    def list_runs(self, limit: int = 20) -> List[PipelineRun]:
        return (self.db.query(PipelineRun)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
                .all())

class ApprovalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, tender_id: str, run_id: str,
               decision: str, reviewer_name: str,
               comments: str = None) -> Approval:
        approval = Approval(
            tender_id=tender_id,
            pipeline_run_id=run_id,
            decision=decision,
            reviewer_name=reviewer_name,
            comments=comments,
        )
        self.db.add(approval)
        self.db.flush()
        return approval
