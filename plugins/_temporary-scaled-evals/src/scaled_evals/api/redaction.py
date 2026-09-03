# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Secret redaction helpers for logs and uploaded text artifacts."""

from __future__ import annotations

import re

_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:policy_api_key|openai_api_key|anthropic_api_key|ngc_inference_api_key|"
    r"daytona_api_key|api[_-]?key|access[_-]?token|sandbox_oc_token|bearer_token|"
    r"authorization|database_url|secret|password)\b\s*[:=]\s*)"
    r"([^,\s'\"}]+)"
)
_TOKEN_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9._-]{8,}|"
    r"sha256~[A-Za-z0-9._~-]{8,}|"
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
)
_DATABASE_URL_RE = re.compile(r"(?i)\b((?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?)://[^\s:/@]+:)([^\s@]+)(@)")


def redact_secret_text(text: str) -> str:
    """Mask common API-key shapes without needing the original secret value."""
    text = _ASSIGNMENT_RE.sub(_redact_assignment, text)
    text = _TOKEN_RE.sub("<redacted>", text)
    return _DATABASE_URL_RE.sub(r"\1<redacted>\3", text)


def _redact_assignment(match: re.Match[str]) -> str:
    value = match.group(2)
    if value.startswith("$"):
        return match.group(0)
    return f"{match.group(1)}<redacted>"
