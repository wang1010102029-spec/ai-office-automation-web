from __future__ import annotations

import logging
import sys
from functools import lru_cache


LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"


@lru_cache(maxsize=1)
def configure_logging(level: int = logging.INFO) -> logging.Logger:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)
    root_logger.setLevel(level)
    return root_logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name or "ai_office_automation_web")
