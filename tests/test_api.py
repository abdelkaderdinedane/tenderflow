"""
TenderFlow Phase 4 — Automated Tests
Run with: pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.models import Base
from app.db.session import get_db
from app.core.config import settings

# ── Test database (SQLite in memory) ──
TEST_DB_URL = "sqlite:///./test_tenderflow.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def api_headers():
    return {"X-API-Key": settings.API_KEY}

DEMO_TENDER = {
    "title": "Smart City Platform for Riyadh Municipality",
    "raw_text": "Tender: Smart City Platform. Client: Riyadh Municipality. Budget: 500000 USD. Deadline: 45 days. Sector: IT/GovTech.",
    "source_type": "manual_text"
}

MOCK_AGENT_RESPONSE = {
    "status": "completed",
    "response": '{"title": "Smart City Platform", "client": "Riyadh Municipality", "budget_usd": 500000, "sector": "IT/GovTech", "days_remaining": 45, "deadline": "45 days", "client_country": "Saudi Arabia", "source": "portal", "language": "EN"}',
    "duration_seconds": 5.0,
    "retry_count": 0,
    "error": None,
}

# ════════════════════════════════════════
# HEALTH CHECK TESTS
# ════════════════════════════════════════
class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_has_required_fields(self, client):
        data = client.get("/api/v1/health").json()
        assert "status" in data
        assert "app" in data
        assert "version" in data
        assert "database" in data

# ════════════════════════════════════════
# AUTHENTICATION TESTS
# ════════════════════════════════════════
class TestAuthentication:
    def test_no_api_key_returns_401(self, client):
        response = client.post("/api/v1/tenders", json=DEMO_TENDER)
        assert response.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        response = client.post(
            "/api/v1/tenders",
            json=DEMO_TENDER,
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    def test_correct_api_key_passes(self, client, api_headers):
        with patch("app.services.tender_service._bg_run_pipeline"):
            response = client.post(
                "/api/v1/tenders",
                json=DEMO_TENDER,
                headers=api_headers
            )
        assert response.status_code == 201

# ════════════════════════════════════════
# TENDER CREATION TESTS
# ════════════════════════════════════════
class TestTenderCreation:
    def test_create_tender_happy_path(self, client, api_headers):
        with patch("app.services.tender_service._bg_run_pipeline"):
            response = client.post(
                "/api/v1/tenders",
                json=DEMO_TENDER,
                headers=api_headers
            )
        assert response.status_code == 201
        data = response.json()
        assert "tender_id" in data
        assert "pipeline_run_id" in data
        assert data["status"] == "pending"
        assert data["tender_id"].startswith("TF-")

    def test_create_tender_empty_title_fails(self, client, api_headers):
        response = client.post(
            "/api/v1/tenders",
            json={"title": "", "raw_text": "Some text"},
            headers=api_headers
        )
        assert response.status_code == 422

    def test_create_tender_short_text_fails(self, client, api_headers):
        response = client.post(
            "/api/v1/tenders",
            json={"title": "Test", "raw_text": "Too short"},
            headers=api_headers
        )
        assert response.status_code == 422

    def test_create_tender_returns_tender_id(self, client, api_headers):
        with patch("app.services.tender_service._bg_run_pipeline"):
            r1 = client.post("/api/v1/tenders", json=DEMO_TENDER, headers=api_headers)
            r2 = client.post("/api/v1/tenders", json=DEMO_TENDER, headers=api_headers)
        assert r1.json()["tender_id"] != r2.json()["tender_id"]

# ════════════════════════════════════════
# PIPELINE STATUS TESTS
# ════════════════════════════════════════
class TestPipelineStatus:
    def _create_tender(self, client, api_headers):
        with patch("app.services.tender_service._bg_run_pipeline"):
            r = client.post("/api/v1/tenders", json=DEMO_TENDER, headers=api_headers)
        return r.json()

    def test_status_returns_correct_structure(self, client, api_headers):
        data = self._create_tender(client, api_headers)
        tender_id = data["tender_id"]
        response = client.get(f"/api/v1/pipeline/{tender_id}/status",
                              headers=api_headers)
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["tender_id"] == tender_id
        assert "pipeline_status" in status_data
        assert "agents" in status_data
        assert "agents_completed" in status_data

    def test_status_unknown_tender_returns_404(self, client, api_headers):
        response = client.get("/api/v1/pipeline/TF-UNKNOWN/status",
                              headers=api_headers)
        assert response.status_code == 404

    def test_status_has_all_7_agents(self, client, api_headers):
        data = self._create_tender(client, api_headers)
        status = client.get(f"/api/v1/pipeline/{data['tender_id']}/status",
                            headers=api_headers).json()
        agents = status["agents"]
        expected = ["intake", "ocr", "gonogo", "compliance",
                    "pricing", "proposal", "tracking"]
        for agent in expected:
            assert agent in agents

# ════════════════════════════════════════
# APPROVAL TESTS
# ════════════════════════════════════════
class TestApproval:
    def _create_tender(self, client, api_headers):
        with patch("app.services.tender_service._bg_run_pipeline"):
            r = client.post("/api/v1/tenders", json=DEMO_TENDER, headers=api_headers)
        return r.json()

    def test_approve_tender(self, client, api_headers):
        data = self._create_tender(client, api_headers)
        response = client.post(
            f"/api/v1/approvals/{data['tender_id']}",
            json={"decision": "approved",
                  "reviewer_name": "Operations Manager",
                  "comments": "All good"},
            headers=api_headers
        )
        assert response.status_code == 200
        result = response.json()
        assert result["decision"] == "approved"
        assert result["reviewer_name"] == "Operations Manager"

    def test_reject_tender(self, client, api_headers):
        data = self._create_tender(client, api_headers)
        response = client.post(
            f"/api/v1/approvals/{data['tender_id']}",
            json={"decision": "rejected",
                  "reviewer_name": "Manager",
                  "comments": "Not suitable"},
            headers=api_headers
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "rejected"

    def test_invalid_decision_fails(self, client, api_headers):
        data = self._create_tender(client, api_headers)
        response = client.post(
            f"/api/v1/approvals/{data['tender_id']}",
            json={"decision": "maybe",
                  "reviewer_name": "Manager"},
            headers=api_headers
        )
        assert response.status_code == 422

    def test_approval_unknown_tender_returns_404(self, client, api_headers):
        response = client.post(
            "/api/v1/approvals/TF-UNKNOWN",
            json={"decision": "approved", "reviewer_name": "Manager"},
            headers=api_headers
        )
        assert response.status_code == 404

# ════════════════════════════════════════
# RUN HISTORY TESTS
# ════════════════════════════════════════
class TestRunHistory:
    def test_runs_returns_list(self, client, api_headers):
        response = client.get("/api/v1/runs", headers=api_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_runs_limit_parameter(self, client, api_headers):
        response = client.get("/api/v1/runs?limit=5", headers=api_headers)
        assert response.status_code == 200

    def test_runs_limit_too_high_fails(self, client, api_headers):
        response = client.get("/api/v1/runs?limit=999", headers=api_headers)
        assert response.status_code == 422

# ════════════════════════════════════════
# AGENT TESTS
# ════════════════════════════════════════
class TestOllamaClient:
    def test_call_agent_success(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"response": "Test response"}
            )
            from app.integrations.ollama_client import call_agent
            result = call_agent("intake", "Test input")
            assert result["status"] == "completed"
            assert result["response"] == "Test response"
            assert result["error"] is None

    def test_call_agent_timeout_triggers_retry(self):
        import requests as req
        with patch("requests.post",
                   side_effect=req.exceptions.Timeout("timeout")):
            from app.integrations.ollama_client import call_agent
            result = call_agent("intake", "Test input", max_retries=1)
            assert result["status"] == "failed"
            assert result["retry_count"] > 0

    def test_call_agent_empty_response_retries(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"response": ""}
            )
            from app.integrations.ollama_client import call_agent
            result = call_agent("intake", "Test", max_retries=1)
            assert result["status"] == "failed"
