# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for carrying anonymous job telemetry context on platform jobs."""

from __future__ import annotations

from typing import Any

TELEMETRY_CUSTOM_FIELDS_KEY = "_nemo_telemetry"
TELEMETRY_SESSION_ID_KEY = "session_id"


def build_job_telemetry_custom_fields(session_id: str) -> dict[str, Any]:
    return {TELEMETRY_CUSTOM_FIELDS_KEY: {TELEMETRY_SESSION_ID_KEY: session_id}}


def get_job_telemetry_session_id(custom_fields: dict[str, Any] | None) -> str | None:
    if not isinstance(custom_fields, dict):
        return None
    telemetry = custom_fields.get(TELEMETRY_CUSTOM_FIELDS_KEY)
    if not isinstance(telemetry, dict):
        return None
    session_id = telemetry.get(TELEMETRY_SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return session_id


def merge_job_telemetry_custom_fields(
    custom_fields: dict[str, Any] | None,
    telemetry_custom_fields: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(custom_fields or {})
    existing = merged.get(TELEMETRY_CUSTOM_FIELDS_KEY)
    telemetry = dict(existing) if isinstance(existing, dict) else {}
    incoming = telemetry_custom_fields.get(TELEMETRY_CUSTOM_FIELDS_KEY)
    if isinstance(incoming, dict):
        telemetry.update(incoming)
    if telemetry:
        merged[TELEMETRY_CUSTOM_FIELDS_KEY] = telemetry
    return merged
