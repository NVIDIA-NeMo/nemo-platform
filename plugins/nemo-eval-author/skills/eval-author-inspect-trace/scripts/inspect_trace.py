# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Print one source-qualified trace analysis bundle as JSON."""

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from overview import build_overview  # noqa: E402

_INTAKE_SOURCE_DIR = _SCRIPTS / "sources" / "intake"
SUPPORTED_SOURCES = ("intake",)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read one source-qualified trace for evidence-based analysis.")
    parser.add_argument("--trace", required=True, help="Source-qualified trace reference, such as intake://traces/ID.")
    parser.add_argument("--compact", action="store_true", help="Print the JSON on one line.")
    return parser


def _source_kind(trace_ref: str) -> str:
    if "://" not in trace_ref:
        raise ValueError("Trace reference must be source-qualified, for example intake://traces/TRACE_ID.")
    try:
        source_kind = urlsplit(trace_ref).scheme.lower()
    except ValueError as exc:
        raise ValueError(f"Trace reference is invalid: {exc}") from exc
    if not source_kind:
        raise ValueError("Trace reference must be source-qualified, for example intake://traces/TRACE_ID.")
    if source_kind not in SUPPORTED_SOURCES:
        raise ValueError(
            f"Trace source '{source_kind}' is not supported. Supported sources: {', '.join(SUPPORTED_SOURCES)}."
        )
    return source_kind


def inspect(trace_ref: str, source_args: list[str]) -> dict[str, Any]:
    """Build the deterministic input for the skill's trace assessment."""
    source_kind = _source_kind(trace_ref)
    _, _, locator = trace_ref.partition("://")
    if source_kind == "intake":
        sys.path.insert(0, str(_INTAKE_SOURCE_DIR))
    adapter = importlib.import_module("adapter")
    source, trace = adapter.read_source(f"{source_kind}://{locator}", source_args)
    identity = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    report_name = hashlib.sha256(identity.encode()).hexdigest()
    return {
        "schema_version": "1",
        "source": source,
        "report_path": f".eval-author/traces/{report_name}.md",
        "trace": trace,
        "overview": build_overview(trace),
    }


def main() -> int:
    args, source_args = _parser().parse_known_args()
    try:
        report = inspect(args.trace, source_args)
        code = 0
    except ValueError as exc:
        report = {
            "schema_version": "1",
            "trace_ref": args.trace,
            "supported_sources": list(SUPPORTED_SOURCES),
            "error": str(exc),
            "hint": "Read the selected source guide and check its requirements, trace reference, and source arguments.",
        }
        code = 1
    json.dump(report, sys.stdout, indent=None if args.compact else 2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
