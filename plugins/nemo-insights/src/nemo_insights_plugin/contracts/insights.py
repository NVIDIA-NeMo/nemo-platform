# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structural contract for the local Insights YAML document."""

from pathlib import Path
from typing import Any

import yaml


class InsightsFileError(ValueError):
    """A shared Insights file is unreadable or structurally invalid."""


def load_insights_document(path: Path) -> dict[str, Any]:
    """Read and validate one existing UTF-8 Insights YAML document."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise InsightsFileError(f"insights file {path} is not valid UTF-8: {exc}") from None
    except OSError as exc:
        raise InsightsFileError(f"insights file {path} is not readable as UTF-8: {exc}") from None
    except yaml.YAMLError as exc:
        raise InsightsFileError(f"insights file {path} must contain valid YAML: {exc}") from None
    if not isinstance(payload, dict):
        raise InsightsFileError(f"insights file {path} must contain a YAML mapping at its root")
    if "insights" in payload:
        records = payload["insights"]
        if not isinstance(records, list):
            raise InsightsFileError(f"insights file {path}: `insights` must be a list")
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise InsightsFileError(f"insights file {path}: `insights` item {index} must be a YAML mapping")
    return dict(payload)


def validate_insights_file(path: Path | None) -> None:
    """Validate an existing file; allow absent optional output files."""
    if path is None:
        return
    try:
        path.stat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InsightsFileError(f"insights file {path} is not readable as UTF-8: {exc}") from None
    load_insights_document(path)
