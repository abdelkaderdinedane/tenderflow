import logging
import json
import time
from datetime import datetime
from contextvars import ContextVar

# Context variable to carry run_id across async calls
current_run_id: ContextVar[str] = ContextVar("current_run_id", default="")
current_tender_id: ContextVar[str] = ContextVar("current_tender_id", default="")

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": current_run_id.get(""),
            "tender_id": current_tender_id.get(""),
        }
        for field in ["agent_name", "event_type", "duration_seconds", "error"]:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger

class Timer:
    def __init__(self):
        self._start = time.time()

    def elapsed(self) -> float:
        return round(time.time() - self._start, 2)
