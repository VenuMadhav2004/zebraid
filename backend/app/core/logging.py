"""Central logging setup. Every record carries the current request id ("-" outside requests)."""
from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure the `app` logger tree. Uvicorn keeps its own handlers."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "loggers": {
                "app": {"handlers": ["console"], "level": level, "propagate": False},
            },
        }
    )
