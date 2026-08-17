import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.integrations.flowise_client import call_agent
from app.repositories.pipeline_repository import PipelineRepository
from app.core.logger import get_logger, Timer, current_run_id, current_tender_id

logger = get_logger("orchestrator")

AGENT_ORDER = ["intake", "ocr", "gonogo", "compliance",
               "pricing", "proposal", "tracking"]

def run_pipeline(tender_id: str, run_id: str, raw_text: str,
                 start_from: str = "intake") -> dict:
    """
    Main orchestration function.
    Creates its own DB session via get_background_db()
    to avoid Phase 3's session lifecycle bug.
    """
    from app.db.session import get_background_db

    # Set context variables for structured logging
    current_run_id.set(run_id)
    current_tender_id.set(tender_id)

    with get_background_db() as db:
        repo = PipelineRepository(db)
        return _execute_pipeline(repo, tender_id, run_id,
                                 raw_text, start_from)

def _execute_pipeline(repo: PipelineRepository, tender_id: str,
                      run_id: str, raw_text: str,
                      start_from: str) -> dict:
    timer = Timer()
    start_index = (AGENT_ORDER.index(start_from)
                   if start_from in AGENT_ORDER else 0)

    shared = _init_shared_json(tender_id, run_id)
    repo.update_run_status(run_id, "in_progress")
    logger.info(f"Pipeline started from {start_from}",
                extra={"event_type": "pipeline_start"})

    results = {}

    def run_agent(name: str, message: str) -> dict:
        repo.upsert_agent_run(run_id, name, "running")
        repo.update_run_status(run_id, "in_progress", current_agent=name)
        result = call_agent(name, message)
        repo.upsert_agent_run(
            run_id, name,
            result["status"],
            response=result["response"],
            duration=result["duration_seconds"],
            error=result["error"],
            attempt=result["retry_count"] + 1,
        )
        return result

    def should_run(agent_name: str) -> bool:
        return AGENT_ORDER.index(agent_name) >= start_index

    # ── INTAKE ──
    if should_run("intake"):
        r = run_agent("intake", raw_text)
        results["intake"] = r
        shared["agent_1_intake"] = _agent_block(r)
        if r["status"] == "failed":
            return _finalize(repo, run_id, shared, timer, "partial")

    # ── OCR ──
    if should_run("ocr"):
        msg = (f"Extract document intelligence from this tender:\n"
               f"{results.get('intake', {}).get('response', '')}\n\n"
               f"Original text:\n{raw_text}")
        r = run_agent("ocr", msg)
        results["ocr"] = r
        shared["agent_2_ocr"] = _agent_block(r)

    # ── GO/NO-GO ──
    if should_run("gonogo"):
        msg = (f"Evaluate this tender opportunity:\n\n"
               f"INTAKE DATA:\n{results.get('intake', {}).get('response', '')}\n\n"
               f"OCR DATA:\n{results.get('ocr', {}).get('response', '')}")
        r = run_agent("gonogo", msg)
        results["gonogo"] = r
        shared["agent_3_gonogo"] = _agent_block(r)

        # Stop if NO-GO
        if r.get("response") and "NO-GO" in r["response"].upper():
            logger.info("Pipeline stopped at Go/No-Go — NO-GO decision",
                        extra={"event_type": "pipeline_no_go"})
            for skipped in ["agent_4_compliance", "agent_5_pricing",
                            "agent_6_proposal"]:
                shared[skipped] = {"status": "skipped", "response": None}
            return _finalize(repo, run_id, shared, timer, "no_go")

    # ── COMPLIANCE + PRICING in parallel ──
    if should_run("compliance"):
        compliance_msg = (
            f"Check compliance for this tender:\n"
            f"INTAKE: {results.get('intake', {}).get('response', '')}\n"
            f"OCR: {results.get('ocr', {}).get('response', '')}\n"
            f"DECISION: {results.get('gonogo', {}).get('response', '')}"
        )
        pricing_msg = (
            f"Estimate cost for this project:\n"
            f"INTAKE: {results.get('intake', {}).get('response', '')}\n"
            f"OCR: {results.get('ocr', {}).get('response', '')}"
        )

        logger.info("Running Compliance + Pricing in parallel",
                    extra={"event_type": "parallel_start"})

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(run_agent, "compliance", compliance_msg): "compliance",
                executor.submit(run_agent, "pricing", pricing_msg): "pricing",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    r = future.result()
                    results[name] = r
                    key = "agent_4_compliance" if name == "compliance" else "agent_5_pricing"
                    shared[key] = _agent_block(r)
                except Exception as e:
                    logger.error(f"Parallel agent {name} exception: {str(e)}")
                    results[name] = {"status": "failed", "response": None,
                                     "duration_seconds": 0, "error": str(e)}

    # ── PROPOSAL ──
    if should_run("proposal"):
        msg = (
            f"Generate a professional proposal for this tender:\n\n"
            f"TENDER DETAILS:\n{results.get('intake', {}).get('response', '')}\n\n"
            f"DECISION: {results.get('gonogo', {}).get('response', '')}\n\n"
            f"COMPLIANCE: {results.get('compliance', {}).get('response', '')}\n\n"
            f"PRICING: {results.get('pricing', {}).get('response', '')}"
        )
        r = run_agent("proposal", msg)
        results["proposal"] = r
        shared["agent_6_proposal"] = _agent_block(r)

    # ── TRACKING ──
    if should_run("tracking"):
        msg = (
            f"Track submission status for this tender:\n\n"
            f"Today: {datetime.utcnow().strftime('%Y-%m-%d')}\n"
            f"TENDER: {results.get('intake', {}).get('response', '')}\n"
            f"COMPLIANCE: {results.get('compliance', {}).get('response', '')}"
        )
        r = run_agent("tracking", msg)
        results["tracking"] = r
        shared["agent_7_tracking"] = _agent_block(r)

    return _finalize(repo, run_id, shared, timer, "waiting_approval")


def _init_shared_json(tender_id: str, run_id: str) -> dict:
    return {
        "schema_version": "4.0",
        "tender_id": tender_id,
        "run_id": run_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "pipeline_status": "in_progress",
        "agent_1_intake":     {"status": "pending"},
        "agent_2_ocr":        {"status": "pending"},
        "agent_3_gonogo":     {"status": "pending"},
        "agent_4_compliance": {"status": "pending"},
        "agent_5_pricing":    {"status": "pending"},
        "agent_6_proposal":   {"status": "pending"},
        "agent_7_tracking":   {"status": "pending"},
    }

def _agent_block(result: dict) -> dict:
    return {
        "status": result["status"],
        "response": result.get("response"),
        "duration_seconds": result.get("duration_seconds"),
        "retry_count": result.get("retry_count", 0),
        "error": result.get("error"),
    }

def _finalize(repo: PipelineRepository, run_id: str,
              shared: dict, timer: Timer, status: str) -> dict:
    shared["pipeline_status"] = status
    shared["completed_at"] = datetime.utcnow().isoformat() + "Z"
    shared["total_duration_seconds"] = timer.elapsed()

    repo.update_run_status(
        run_id, status,
        result_json=json.dumps(shared, ensure_ascii=False)
    )
    logger.info(f"Pipeline finalized — status={status} "
                f"duration={shared['total_duration_seconds']}s",
                extra={"event_type": "pipeline_complete",
                       "duration_seconds": shared["total_duration_seconds"]})
    return shared
