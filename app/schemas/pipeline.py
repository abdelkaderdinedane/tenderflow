from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class SourceType(str, Enum):
    manual_text = "manual_text"
    email = "email"
    portal = "portal"
    upload = "upload"

class PipelineStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    waiting_approval = "waiting_approval"
    completed = "completed"
    completed_with_approval = "completed_with_approval"
    no_go = "no_go"
    failed = "failed"
    partial = "partial"
    rejected = "rejected"

class AgentStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"

class ApprovalDecision(str, Enum):
    approved = "approved"
    rejected = "rejected"

# ── Tender ──
class TenderCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=512,
                       description="Tender title")
    raw_text: str = Field(..., min_length=10,
                          description="Full tender description or raw text")
    source_type: SourceType = SourceType.manual_text

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace")
        return v.strip()

class TenderCreateResponse(BaseModel):
    tender_id: str
    pipeline_run_id: str
    status: PipelineStatus
    message: str = "Pipeline started successfully"

# ── Pipeline ──
class PipelineStartRequest(BaseModel):
    start_from: str = Field("intake", description="Agent name to start from")
    parallel_compliance_pricing: bool = True

class AgentStatusDetail(BaseModel):
    status: AgentStatus
    duration_seconds: Optional[float] = None
    attempt_number: Optional[int] = None
    error: Optional[str] = None

class PipelineStatusResponse(BaseModel):
    tender_id: str
    run_id: str
    pipeline_status: PipelineStatus
    current_agent: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    agents: Dict[str, AgentStatusDetail]
    agents_completed: int
    agents_total: int = 7

class PipelineResumeRequest(BaseModel):
    start_from: str = Field(..., description="Agent name to resume from")

class PipelineResult(BaseModel):
    tender_id: str
    run_id: str
    pipeline_status: PipelineStatus
    total_duration_seconds: float
    agents_completed: int
    agents_total: int
    result: Dict[str, Any]

# ── Approval ──
class ApprovalRequest(BaseModel):
    decision: ApprovalDecision
    reviewer_name: str = Field(..., min_length=2, max_length=128)
    comments: Optional[str] = Field(None, max_length=2000)

class ApprovalResponse(BaseModel):
    tender_id: str
    pipeline_run_id: str
    decision: ApprovalDecision
    reviewer_name: str
    comments: Optional[str]
    created_at: datetime

# ── Run History ──
class RunSummary(BaseModel):
    run_id: str
    tender_id: str
    title: Optional[str] = None
    status: PipelineStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    agents_completed: int = 0

# ── Health ──
class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    timestamp: str
    database: str
    ollama: str

# ── Error ──
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str
