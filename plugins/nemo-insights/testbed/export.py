# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Drain the intake read API into per-workspace JSONL files (bundle capture).

The capture side of testbed export bundles: for each workspace, page ALL spans
(``mode="detailed"``), annotations, and evaluator results through the platform
SDK — exactly the surface the analyst's remote backend reads — and write one
JSON document per line under ``<out_dir>/export/<workspace>/``.

Every query carries an explicit lower bound (``since``, else epoch): the read
API silently injects a 30-day default lookback when none is given, so an
"unbounded" drain would quietly lose older spans.
"""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.config.config import Config

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
PAGE_SIZE = 200  # generous pages: drain-all in few round-trips

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def make_client(base_url: str) -> AsyncNeMoPlatform:
    """Async SDK client; platform auth only for remote URLs (mirrors ingest's client)."""
    host = (urlparse(base_url).hostname or "").lower()
    config_path = Config.get_default_config_path()
    if host in _LOOPBACK_HOSTS or not config_path.exists():
        return AsyncNeMoPlatform(base_url=base_url, timeout=60.0)
    return AsyncNeMoPlatform(base_url=base_url, config_path=config_path, timeout=60.0)


def _dump(item) -> dict:
    """One SDK model -> plain JSON-able dict (drop null fields, like the analyst does)."""
    return item.model_dump(mode="json", exclude_none=True)


async def _drain_to_jsonl(paginator, path: Path, *, on_doc: Callable[[dict], None] | None = None) -> int:
    """Write every paginated doc to *path*, one JSON document per line; return the count."""
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        async for item in paginator:
            doc = _dump(item)
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            if on_doc is not None:
                on_doc(doc)
            count += 1
    return count


class _StartBounds:
    """Min/max span ``started_at`` across everything exported (manifest time bounds)."""

    def __init__(self) -> None:
        self.min: datetime | None = None
        self.max: datetime | None = None

    def note(self, doc: dict) -> None:
        raw = doc.get("started_at")
        if not raw:
            return
        try:
            ts = datetime.fromisoformat(str(raw))
        except ValueError:
            return
        if self.min is None or ts < self.min:
            self.min = ts
        if self.max is None or ts > self.max:
            self.max = ts


def export_workspaces(base_url: str, workspaces: list[str], out_dir: Path, *, since: datetime | None) -> dict:
    """Drain spans/annotations/evaluator-results per workspace into JSONL files.

    Writes ``out_dir/export/<workspace>/{spans,annotations,evaluator_results}.jsonl``
    and returns ``{"workspaces": {ws: {collection: count}}, "min_start_time": ...,
    "max_start_time": ...}`` (time bounds from span ``started_at``; ISO strings or
    None when no spans matched).
    """
    return asyncio.run(_export_workspaces(base_url, workspaces, out_dir, since=since))


async def _export_workspaces(base_url: str, workspaces: list[str], out_dir: Path, *, since: datetime | None) -> dict:
    lower = (since or EPOCH).isoformat()
    bounds = _StartBounds()
    counts: dict[str, dict[str, int]] = {}
    client = make_client(base_url)
    try:
        for workspace in workspaces:
            ws_dir = out_dir / "export" / workspace
            ws_dir.mkdir(parents=True, exist_ok=True)
            spans = client.intake.spans.list(
                workspace=workspace,
                page_size=PAGE_SIZE,
                mode="detailed",
                sort="started_at",
                filter=cast(Any, {"started_at": {"gte": lower}}),
            )
            n_spans = await _drain_to_jsonl(spans, ws_dir / "spans.jsonl", on_doc=bounds.note)
            annotations = client.intake.annotations.list(
                workspace=workspace,
                page_size=PAGE_SIZE,
                sort="created_at",
                filter=cast(Any, {"created_at": {"gte": lower}}),
            )
            n_annotations = await _drain_to_jsonl(annotations, ws_dir / "annotations.jsonl")
            results = client.intake.evaluator_results.list(
                workspace=workspace,
                page_size=PAGE_SIZE,
                sort="created_at",
                filter=cast(Any, {"created_at": {"gte": lower}}),
            )
            n_results = await _drain_to_jsonl(results, ws_dir / "evaluator_results.jsonl")
            counts[workspace] = {
                "spans": n_spans,
                "annotations": n_annotations,
                "evaluator_results": n_results,
            }
            print(f"exported {workspace}: {n_spans} spans, {n_annotations} annotations, {n_results} evaluator results")
    finally:
        await client.close()
    return {
        "workspaces": counts,
        "min_start_time": bounds.min.isoformat() if bounds.min else None,
        "max_start_time": bounds.max.isoformat() if bounds.max else None,
    }
