# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt Intake to the three reads an inspection makes: list, overview, and spans.

The entry point stays free of Intake's flags, credentials, and client. Everything
source-specific lives here, so a second trace source can be added beside this module
without changing the entry point.
"""

import argparse
from typing import Any, NoReturn

from sources.intake._http import IntakeClient, IntakeError
from sources.intake.reader import DEFAULT_MAX_CHARS, DEFAULT_SPAN_LIMIT, read_overview, read_spans
from sources.intake.traces import DEFAULT_TRACE_LIMIT, find_agent_traces, recent_traces


class _ArgumentParser(argparse.ArgumentParser):
    """Raise instead of exiting, so a usage error reports the documented error object."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(f"Intake source arguments are invalid: {message}")


def _bound(value: str) -> int:
    """Accept only a positive bound, because the alternatives fail silently.

    A negative ``--max-chars`` slices a payload from the end and still marks the field
    truncated, so the caller quotes mangled evidence as if it were the leading text. A
    non-positive ``--limit`` selects nothing and reads as an empty trace.
    """
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or greater, not {number}")
    return number


def _client(arguments: list[str], build: Any) -> tuple[IntakeClient, argparse.Namespace]:
    parser = _ArgumentParser(add_help=False)
    parser.add_argument("--workspace", required=True)
    build(parser)
    args = parser.parse_args(arguments)
    try:
        return IntakeClient.from_env(args.workspace), args
    except IntakeError as exc:
        raise ValueError(str(exc)) from exc


def _source(client: IntakeClient, **context: Any) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "platform_origin": client.base_url,
        "workspace": client.workspace,
    }
    identity.update({key: value for key, value in context.items() if value is not None})
    return {"kind": "intake", "context": identity}


def list_traces(arguments: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """List candidate Intake traces so an inspection can name a real one."""

    def build(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--agent")
        parser.add_argument("--since")
        parser.add_argument("--limit", type=_bound, default=DEFAULT_TRACE_LIMIT)

    client, args = _client(arguments, build)
    try:
        if args.agent:
            found = find_agent_traces(client, args.agent, since=args.since, limit=args.limit)
        else:
            found = recent_traces(client, since=args.since, limit=args.limit)
    except IntakeError as exc:
        raise ValueError(str(exc)) from exc
    return _source(client, agent=args.agent, since=args.since), found


def overview(trace_ref: str, arguments: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one Intake trace's structure without paying for its span payloads."""
    client, _ = _client(arguments, lambda parser: None)
    try:
        trace = read_overview(client, trace_ref)
    except IntakeError as exc:
        raise ValueError(str(exc)) from exc
    source = _source(client)
    source["trace_ref"] = trace["trace_ref"]
    return source, trace


def spans(trace_ref: str, arguments: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read detailed payloads for a named slice of one Intake trace's spans."""

    def build(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--status")
        parser.add_argument("--kind")
        parser.add_argument("--parent")
        parser.add_argument("--span-id", action="append", default=[], dest="span_ids")
        parser.add_argument("--limit", type=_bound, default=DEFAULT_SPAN_LIMIT)
        parser.add_argument("--max-chars", type=_bound, default=DEFAULT_MAX_CHARS)
        parser.add_argument("--full", action="store_true")

    client, args = _client(arguments, build)
    try:
        selected = read_spans(
            client,
            trace_ref,
            status=args.status,
            kind=args.kind,
            parent_span_id=args.parent,
            span_ids=args.span_ids,
            limit=args.limit,
            max_chars=None if args.full else args.max_chars,
        )
    except IntakeError as exc:
        raise ValueError(str(exc)) from exc
    source = _source(client)
    source["trace_ref"] = selected["trace_ref"]
    return source, selected
