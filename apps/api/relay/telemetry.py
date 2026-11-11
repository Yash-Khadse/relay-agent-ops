import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("execution_id", "error_type", "correlation_id"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
