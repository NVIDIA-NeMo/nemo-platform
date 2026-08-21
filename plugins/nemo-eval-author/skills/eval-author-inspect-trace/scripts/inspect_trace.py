# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Print one Intake trace analysis bundle as JSON."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_INTAKE_SCRIPTS = Path(__file__).resolve().parents[2] / "eval-author" / "scripts" / "intake"
sys.path.insert(0, str(_INTAKE_SCRIPTS))

from _http import IntakeClient, IntakeError  # noqa: E402  # ty: ignore[unresolved-import]
from overview import build_overview  # noqa: E402  # ty: ignore[unresolved-import]
from reader import read_trace  # noqa: E402  # ty: ignore[unresolved-import]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read one Intake trace for evidence-based analysis.")
    parser.add_argument("--workspace", required=True, help="Workspace that contains the trace.")
    parser.add_argument("--trace", required=True, help="Bare trace ID or intake:// trace reference.")
    parser.add_argument("--compact", action="store_true", help="Print the JSON on one line.")
    return parser


def inspect(workspace: str, trace_ref: str) -> dict[str, Any]:
    """Build the deterministic input for the skill's trace assessment."""
    client = IntakeClient.from_env(workspace)
    trace = read_trace(client, trace_ref)
    identity = json.dumps(
        [client.base_url, client.workspace, str(trace["trace_id"])],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    report_name = hashlib.sha256(identity.encode()).hexdigest()
    return {
        "schema_version": "1",
        "workspace": workspace,
        "platform_origin": client.base_url,
        "report_path": f".eval-author/traces/{report_name}.md",
        "trace": trace,
        "overview": build_overview(trace),
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        report = inspect(args.workspace, args.trace)
        code = 0
    except (IntakeError, ValueError) as exc:
        report = {
            "schema_version": "1",
            "workspace": args.workspace,
            "trace_ref": args.trace,
            "error": str(exc),
            "hint": "Check NMP_BASE_URL, NMP_ACCESS_TOKEN, the workspace, and the trace ID.",
        }
        code = 1
    json.dump(report, sys.stdout, indent=None if args.compact else 2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
