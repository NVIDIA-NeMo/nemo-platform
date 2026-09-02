# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Default outbound headers for supported inference clients."""

from __future__ import annotations

import json
from collections.abc import Mapping

INFERENCE_PRIORITY_HEADER = "X-Inference-Priority"
INFERENCE_PRIORITY_VALUE = "batch"
INFERENCE_HEADERS_ENV = "SCALED_EVALS_INFERENCE_HEADERS_JSON"


def with_default_inference_priority(
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return headers with the platform batch-priority default enforced."""
    merged = {
        str(name): str(value)
        for name, value in (headers or {}).items()
        if str(name).lower() != INFERENCE_PRIORITY_HEADER.lower()
    }
    merged[INFERENCE_PRIORITY_HEADER] = INFERENCE_PRIORITY_VALUE
    return merged


def with_default_anthropic_custom_headers(value: str | None = None) -> str:
    """Merge the default into Claude's newline-delimited header format."""
    retained: list[str] = []
    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        name, separator, _ = line.partition(":")
        if separator and name.strip().lower() == INFERENCE_PRIORITY_HEADER.lower():
            continue
        if line:
            retained.append(line)
    retained.append(f"{INFERENCE_PRIORITY_HEADER}: {INFERENCE_PRIORITY_VALUE}")
    return "\n".join(retained)


def inference_header_runner_env(
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Render headers for the supported Claude and Codex adapters."""
    merged = with_default_inference_priority(headers)
    toml = ", ".join(f"{json.dumps(name)}={json.dumps(value)}" for name, value in merged.items())
    return {
        INFERENCE_HEADERS_ENV: json.dumps(merged, separators=(",", ":"), sort_keys=True),
        "ANTHROPIC_CUSTOM_HEADERS": "\n".join(f"{name}: {value}" for name, value in merged.items()),
        "CODEX_GATEWAY_HTTP_HEADERS_TOML": "{" + toml + "}",
        "CODEX_GATEWAY_HTTP_HEADERS_JSON": json.dumps(
            merged,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def headers_from_json(value: str | None) -> dict[str, str]:
    """Parse a string-to-string header object from a profile value."""
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or not all(
        isinstance(name, str) and isinstance(header_value, str) for name, header_value in parsed.items()
    ):
        raise ValueError("header JSON must be an object of strings")
    return parsed
