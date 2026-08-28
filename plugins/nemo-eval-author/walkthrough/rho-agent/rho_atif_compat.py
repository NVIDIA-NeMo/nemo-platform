#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Convert rho-agent's legacy Harbor trace to current ATIF v1.6."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def convert(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, sort_keys=True).encode()
    metadata = payload.get("metadata") or {}
    steps = []
    for step_id, source in enumerate(payload.get("steps") or [], start=1):
        step: dict[str, Any] = {
            "step_id": step_id,
            "source": source["source"],
            "message": source.get("message") or "",
        }
        calls = source.get("tool_calls") or []
        if calls:
            step["tool_calls"] = [
                {
                    "tool_call_id": call["call_id"],
                    "function_name": call["name"],
                    "arguments": call.get("arguments") or {},
                }
                for call in calls
            ]
        observations = source.get("observations") or []
        if observations:
            step["observation"] = {
                "results": [
                    {
                        "source_call_id": observation["source_call_id"],
                        "content": observation.get("content") or "",
                    }
                    for observation in observations
                ]
            }
        steps.append(step)

    return {
        "schema_version": "ATIF-v1.6",
        "session_id": hashlib.sha256(encoded).hexdigest()[:12],
        "agent": {
            "name": "rho-agent",
            "version": "04b9cfa",
            "model_name": metadata.get("model") or "unknown",
        },
        "steps": steps,
    }


def main() -> None:
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(convert(payload), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
