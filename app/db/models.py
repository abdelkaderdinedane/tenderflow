from sqlalchemy import (Column, String, Text, Float, Integer,
                        Boolean, DateTime, ForeignKey, Index)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

class Tender(Base):
    __tablename__ = "tenders"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    tender_id   = Column(String(64), unique=True, nullable=False, default=generate_uuid)
    title       = Column(String(512), nullable=False)
    raw_text    = Column(Text, nullable=False)
    source_type = Column(String(64), default="manual_text", nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by  = Column(String(128), default="system", nullable=False)

    runs      = relationship("PipelineRun", back_populates="tender",
                             cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="tender",
                             cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tenders_tender_id", "tender_id"),
        Index("ix_tenders_created_at", "created_at"),
    )

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    run_id        = Column(String(64), unique=True, nullable=False, default=generate_uuid)
    tender_id     = Column(String(64), ForeignKey("tenders.tender_id",
                           ondelete="CASCADE"), nullable=False)
    status        = Column(String(64), default="pending", nullable=False)
    current_agent = Column(String(64), nullable=True)
    started_at    = Column(DateTime, nullable=True)
    completed_at  = Column(DateTime, nullable=True)
    error_summary = Column(Text, nullable=True)
    result_json   = Column(Text, nullable=True)

    tender     = relationship("Tender", back_populates="runs")
    agent_runs = relationship("AgentRun", back_populates="pipeline_run",
                              cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pipeline_runs_run_id", "run_id"),
        Index("ix_pipeline_runs_tender_id", "tender_id"),
        Index("ix_pipeline_runs_status", "status"),
    )

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id     = Column(String(64), ForeignKey("pipeline_runs.run_id",
                                 ondelete="CASCADE"), nullable=False)
    agent_name          = Column(String(64), nullable=False)
    attempt_number      = Column(Integer, default=1, nullable=False)
    status              = Column(String(32), default="pending", nullable=False)
    started_at          = Column(DateTime, nullable=True)
    completed_at        = Column(DateTime, nullable=True)
    duration_seconds    = Column(Float, nullable=True)
    request_payload     = Column(Text, nullable=True)
    raw_response        = Column(Text, nullable=True)
    normalized_response = Column(Text, nullable=True)
    validation_success  = Column(Boolean, default=True, nullable=False)
    validation_errors   = Column(Text, nullable=True)
    error_message       = Column(Text, nullable=True)

    pipeline_run = relationship("PipelineRun", back_populates="agent_runs")

    __table_args__ = (
        Index("ix_agent_runs_pipeline_run_id", "pipeline_run_id"),
        Index("ix_agent_runs_agent_name", "agent_name"),
        Index("ix_agent_runs_status", "status"),
    )

class Approval(Base):
    __tablename__ = "approvals"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    tender_id       = Column(String(64), ForeignKey("tenders.tender_id",
                             ondelete="CASCADE"), nullable=False)
    pipeline_run_id = Column(String(64), nullable=False)
    decision        = Column(String(32), nullable=False)
    reviewer_name   = Column(String(128), nullable=False)
    comments        = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)

    tender = relationship("Tender", back_populates="approvals")

    __table_args__ = (
        Index("ix_approvals_tender_id", "tender_id"),
    )
