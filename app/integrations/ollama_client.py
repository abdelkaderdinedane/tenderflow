import requests
import time
from app.core.config import settings
from app.core.logger import get_logger, Timer

logger = get_logger("flowise_client")

AGENT_IDS = {
    "intake":     settings.FLOWISE_AGENT_INTAKE,
    "ocr":        settings.FLOWISE_AGENT_OCR,
    "gonogo":     settings.FLOWISE_AGENT_GONOGO,
    "compliance": settings.FLOWISE_AGENT_COMPLIANCE,
    "pricing":    settings.FLOWISE_AGENT_PRICING,
    "proposal":   settings.FLOWISE_AGENT_PROPOSAL,
    "tracking":   settings.FLOWISE_AGENT_TRACKING,
}

def call_agent(agent_name: str, message: str,
               max_retries: int = None) -> dict:
    max_retries = max_retries if max_retries is not None else settings.AGENT_MAX_RETRIES
    agent_id = AGENT_IDS.get(agent_name)
    url = f"{settings.FLOWISE_BASE_URL}/api/v1/prediction/{agent_id}"

    timer = Timer()
    retry_count = 0
    last_error = None

    while retry_count <= max_retries:
        try:
            logger.info(f"Calling Flowise agent: {agent_name}",
                       extra={"agent_name": agent_name,
                              "event_type": "agent_call"})
            response = requests.post(
                url,
                json={"question": message},
                timeout=settings.AGENT_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            answer = result.get("text", result.get("answer", str(result)))

            if not answer:
                raise ValueError("Empty response from Flowise")

            duration = timer.elapsed()
            logger.info(f"Agent {agent_name} completed in {duration}s",
                       extra={"agent_name": agent_name,
                              "duration_seconds": duration,
                              "event_type": "agent_success"})
            return {
                "status": "completed",
                "response": answer,
                "duration_seconds": duration,
                "retry_count": retry_count,
                "error": None,
            }

        except requests.exceptions.Timeout:
            last_error = f"Timeout after {settings.AGENT_TIMEOUT}s"
            retry_count += 1
            logger.warning(f"Agent {agent_name} timeout — retry {retry_count}",
                          extra={"agent_name": agent_name,
                                 "event_type": "agent_timeout"})
        except Exception as e:
            last_error = str(e)
            retry_count += 1
            logger.error(f"Agent {agent_name} error: {last_error}",
                        extra={"agent_name": agent_name,
                               "event_type": "agent_error"})

        if retry_count <= max_retries:
            time.sleep(settings.AGENT_RETRY_WAIT)

    duration = timer.elapsed()
    return {
        "status": "failed",
        "response": None,
        "duration_seconds": duration,
        "retry_count": retry_count,
        "error": last_error,
    }