# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration for the safe-synthesizer task.

This module provides JSON-formatted logging configuration for the safe-synthesizer service.
"""

import json
import logging
import os
import sys
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter that properly escapes message content."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure logging to write JSON records to stderr and optional job log file."""
    structured_formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    level_name = log_level.upper()
    valid_levels = logging.getLevelNamesMapping()
    if level_name not in valid_levels:
        allowed = ", ".join(sorted(valid_levels))
        raise ValueError(f"Invalid log level {log_level!r}. Expected one of: {allowed}")
    level = valid_levels[level_name]

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(structured_formatter)
    root_logger.addHandler(stderr_handler)

    log_path = os.environ.get("NEMO_JOB_LOG_PATH")
    if log_path:
        log_dir = Path(log_path)
        log_file = log_dir / "application.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(structured_formatter)
        root_logger.addHandler(file_handler)

    for logger_name in ["safe_synthesizer", "nemo_safe_synthesizer"]:
        logging.getLogger(logger_name).setLevel(level)
