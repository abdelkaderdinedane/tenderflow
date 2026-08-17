from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os
import time

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import create_tables
from app.api.routes import (
    tenders_router, pipeline_router,
    approvals_router, runs_router, health_router
)

logger = get_logger("main")

app = FastAPI(
    title="TenderFlow MVP",
    description="""
## TenderFlow AI-powered Tender Management Platform

### Authentication
All endpoints (except /api/v1/health) require an API key in the header:
```
X-API-Key: your-api-key
```

### Pipeline Flow
1. POST /api/v1/tenders — Submit tender, pipeline starts automatically
2. GET /api/v1/pipeline/{id}/status — Monitor progress
3. GET /api/v1/pipeline/{id}/result — Get full AI analysis
4. POST /api/v1/approvals/{id} — Approve or reject proposal
5. GET /api/v1/runs — View run history
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Request timing middleware ──
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round(time.time() - start, 3)
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} ({duration}s)",
        extra={"event_type": "http_request"}
    )
    return response

# ── Global exception handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error",
                 "detail": str(exc) if settings.DEBUG else "Contact support"}
    )

# ── Routers ──
app.include_router(tenders_router)
app.include_router(pipeline_router)
app.include_router(approvals_router)
app.include_router(runs_router)
app.include_router(health_router)

# ── Frontend ──
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(os.path.join(frontend_path, "index.html"))

@app.on_event("startup")
def startup():
    create_tables()
    logger.info(f"TenderFlow {settings.APP_VERSION} started",
                extra={"event_type": "startup"})
    print(f"\n{'='*50}")
    print(f"  TenderFlow MVP v{settings.APP_VERSION}")
    print(f"  Dashboard : http://localhost:8000")
    print(f"  API Docs  : http://localhost:8000/docs")
    print(f"  Health    : http://localhost:8000/api/v1/health")
    print(f"{'='*50}\n")
