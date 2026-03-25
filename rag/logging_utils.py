"""
Logging helpers for the local context RAG project.
"""

from __future__ import annotations

import logging
import os
import sys


def configure_logging(default_level: str = "INFO") -> None:
    """Configure process-wide logging to stderr."""
    level_name = os.getenv("LOG_LEVEL", default_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        for handler in root_logger.handlers:
            handler.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
    )
