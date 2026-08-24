# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read one trace source as JSON, in the three steps an inspection actually takes.

``list`` finds a trace worth reading. ``overview`` reports the whole shape of one
trace cheaply. ``spans`` spends detail only on the spans you name. Splitting the read
this way keeps the first look affordable on a trace of any size, and it leaves the
choice of what to read in full with the caller rather than with this script.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from overview import build_overview, build_timeline  # noqa: E402
from sources.intake.adapter import list_traces as list_intake  # noqa: E402
from sources.intake.adapter import overview as overview_intake  # noqa: E402
from sources.intake.adapter import spans as spans_intake  # noqa: E402

# One entry per trace source, kept in two maps because discovery takes no trace
# reference and a read takes nothing else. A new source is added to both, beside its
# own package under sources/.
LIST_SOURCES = {"intake": list_intake}
READ_SOURCES = {
    "overview": {"intake": overview_intake},
    "spans": {"intake": spans_intake},
}
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class _ArgumentParser(argparse.ArgumentParser):
    """Raise instead of exiting, so a usage error reports the documented error object."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(f"Arguments are invalid: {message}")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Read one source-qualified trace for evidence-based analysis.")
    verbs = parser.add_subparsers(dest="verb", required=True)

    listing = verbs.add_parser("list", help="List candidate traces from one source.")
    listing.add_argument("--source", required=True, choices=sorted(LIST_SOURCES), help="Trace source to search.")
    listing.add_argument("--compact", action="store_true", help="Print the JSON on one line.")

    for verb, help_text in (
        ("overview", "Report one trace's structure, timeline, and evaluator signals."),
        ("spans", "Read detailed payloads for the spans you name."),
    ):
        read = verbs.add_parser(verb, help=help_text)
        read.add_argument("--trace", required=True, help="Source-qualified reference, such as intake://traces/ID.")
        read.add_argument("--compact", action="store_true", help="Print the JSON on one line.")
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
    if source_kind not in LIST_SOURCES:
        raise ValueError(
            f"Trace source '{source_kind}' is not supported. Supported sources: {', '.join(LIST_SOURCES)}."
        )
    return source_kind


def _report_name(source: dict[str, Any]) -> str:
    """Name the report after its source identity, without a path character in it."""
    trace_id = source["trace_ref"].rpartition("/")[2]
    workspace = source.get("context", {}).get("workspace", "")
    slug = _UNSAFE_NAME.sub("-", f"{source['kind']}-{workspace}-{trace_id}").strip("-.")
    return slug[:96] or "trace"


def read(verb: str, trace_ref: str, source_args: list[str]) -> dict[str, Any]:
    """Run one verb against the source named by the trace reference."""
    source_kind = _source_kind(trace_ref)
    _, _, locator = trace_ref.partition("://")
    source, payload = READ_SOURCES[verb][source_kind](f"{source_kind}://{locator}", source_args)
    report: dict[str, Any] = {"schema_version": "1", "source": source}
    if verb == "overview":
        report["report_path"] = f".eval-author/traces/{_report_name(source)}.md"
        report["overview"] = build_overview(payload)
        report["timeline"] = build_timeline(payload)
        return report
    report.update({key: value for key, value in payload.items() if key != "trace_ref"})
    return report


def find(source_kind: str, source_args: list[str]) -> dict[str, Any]:
    """List the traces one source can offer for inspection."""
    if source_kind not in LIST_SOURCES:
        raise ValueError(
            f"Trace source '{source_kind}' is not supported. Supported sources: {', '.join(LIST_SOURCES)}."
        )
    source, found = LIST_SOURCES[source_kind](source_args)
    return {"schema_version": "1", "source": source, **found}


def main() -> int:
    compact = False
    try:
        args, source_args = _parser().parse_known_args()
        compact = args.compact
        report = find(args.source, source_args) if args.verb == "list" else read(args.verb, args.trace, source_args)
        code = 0
    except ValueError as exc:
        report = {
            "schema_version": "1",
            "supported_sources": list(LIST_SOURCES),
            "error": str(exc),
            "hint": "Read the selected source guide and check its requirements, trace reference, and source arguments.",
        }
        code = 1
    json.dump(report, sys.stdout, indent=None if compact else 2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
