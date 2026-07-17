# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data-access backend for the analyst's tools and final change-set.

Every tool talks to the platform through one :class:`AnalystBackend`, built
once per run by the CLI and shared via ``AnalystDeps`` instead of threading a
raw SDK client around. The backend owns the SDK client and exposes:

- read-only Intake queries (spans, span groups, feedback annotations, and a
  span-rollup session count),
- ``list_insights`` so the analyst can see what already exists, and
- ``persist_result``: the single write entry point that takes the analyst's
  :class:`~nemo_insights_plugin.analyst.result.AnalystResult` and stores it.

Intake reads (spans, span groups, annotations, session count) always hit the
live platform. Insight listing and result persistence vary by backend, because the
target deployment may not have the Insights plugin installed.
:class:`RemoteAnalystBackend` lists insights via the plugin API and persists the
result as Insight rows via the plugin API.
:class:`LocalAnalystBackend` lists from and persists to a local YAML file
(``--insights-file-output``), merging each run's change-set into the file rather
than overwriting it. :func:`make_analyst_backend` picks one. The client's
lifecycle is owned by the caller (the CLI), so the backend never closes it.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import yaml
from nemo_insights_plugin.analyst.result import AnalystResult
from nemo_insights_plugin.entities import Insight, InsightStatus
from nemo_insights_plugin.schema import InsightPage
from nemo_platform import AsyncNeMoPlatform, omit
from nemo_platform_plugin.schema import PaginationData


class InsightNotFoundError(Exception):
    """No insight with the given id exists in the workspace."""


def _dump(item) -> dict:
    """Serialize one SDK model to a plain JSON-able dict (drop null fields)."""
    return item.model_dump(mode="json", exclude_none=True)


def _union_refs(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """Append *new* refs to *existing*, de-duplicating and preserving order."""
    merged = list(existing or [])
    seen = set(merged)
    for ref in new or []:
        if ref not in seen:
            merged.append(ref)
            seen.add(ref)
    return merged


async def _drain(paginator, *, limit: int) -> tuple[list, bool]:
    """Pull up to *limit* items across pages; return ``(items, truncated)``.

    ``truncated`` is True when the stream still had more items than *limit*,
    so the model knows it is looking at a capped view and can narrow its
    filter or raise the limit.
    """
    items: list = []
    truncated = False
    async for item in paginator:
        if len(items) >= limit:
            truncated = True
            break
        items.append(item)
    return items, truncated


def _page_size_for(limit: int) -> int:
    """Per-page size for a drain: big enough to minimize round-trips."""
    return max(1, min(limit, 100))


def _merge_since_filter(filter_obj: dict | None, *, since: datetime | None) -> dict | None:
    """Return *filter_obj* with an enforced ``started_at >= since`` lower bound."""
    return _merge_datetime_lower_bound(filter_obj, key="started_at", since=since)


def _merge_created_since_filter(filter_obj: dict | None, *, since: datetime | None) -> dict | None:
    """Return *filter_obj* with an enforced ``created_at >= since`` lower bound."""
    return _merge_datetime_lower_bound(filter_obj, key="created_at", since=since)


def _merge_datetime_lower_bound(filter_obj: dict | None, *, key: str, since: datetime | None) -> dict | None:
    if since is None:
        return filter_obj

    merged: dict = dict(filter_obj or {})
    existing = merged.get(key)
    lower_bound = since.isoformat()
    if isinstance(existing, dict):
        existing = dict(existing)
        current = existing.get("gte")
        current_datetime = _parse_datetime(current)
        since_datetime = _parse_datetime(since)
        if current_datetime is None or since_datetime is None or current_datetime < since_datetime:
            existing["gte"] = lower_bound
        merged[key] = existing
    else:
        merged[key] = {"gte": lower_bound}
    return merged


def _parse_datetime(value: object) -> datetime | None:
    """Parse a datetime-like lower bound and normalize it to UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _merge_eval_filter(filter_obj: dict | None, *, evaluation_id: str | None) -> dict | None:
    """AND-pin the run scope onto a span filter.

    Mirrors ``_merge_since_filter``: a set ``evaluation_id`` is forced onto every
    read (overwriting any model-supplied value), so a run-scoped analyst never
    reads across runs that share a workspace. ``None`` is a no-op.
    """
    if evaluation_id is None:
        return filter_obj
    merged: dict = dict(filter_obj or {})
    merged["evaluation_id"] = evaluation_id
    return merged


class AnalystBackend(ABC):
    """Read-only Intake access (shared) plus pluggable result persistence.

    The read surface is a thin, uniform pass-through over the Intake SDK: every
    list method takes the raw Intake ``filter`` dict and ``sort`` field and
    drains pages up to ``limit``, and there are get-by-id and evaluator-score
    primitives. The analyst composes these in ``run_code`` rather than relying
    on a wide catalog of narrow tools. Reads always hit the live platform, even
    in local insights mode.
    """

    def __init__(self, client: AsyncNeMoPlatform) -> None:
        self.client = client

    # -- reads: always against the live platform -------------------------- #

    async def count_agent_sessions(
        self,
        *,
        agent: str,
        workspace: str,
        since: datetime | None = None,
        evaluation_id: str | None = None,
    ) -> int:
        """Count distinct sessions (the agent's "traces") via the span rollup.

        Intake has no agent-scoped trace count — only spans carry the agent
        identity — so a "trace" is one distinct ``session_id`` among the agent's
        spans. This rolls those spans up server-side with :meth:`list_span_groups`
        and reports the full distinct-group ``total``.
        """
        groups = await self.list_span_groups(
            workspace=workspace,
            filter={"agent_name": agent},
            group_by="session_id",
            limit=1,
            since=since,
            evaluation_id=evaluation_id,
        )
        return groups["total"]

    async def list_spans(
        self,
        *,
        workspace: str,
        filter: dict | None,
        sort: str,
        mode: str,
        limit: int,
        since: datetime | None = None,
        evaluation_id: str | None = None,
    ) -> dict:
        effective_filter = _merge_eval_filter(_merge_since_filter(filter, since=since), evaluation_id=evaluation_id)
        paginator = self.client.intake.spans.list(
            workspace=workspace,
            page_size=_page_size_for(limit),
            sort=cast(Any, sort),
            filter=cast(Any, effective_filter) or omit,
            mode=cast(Any, mode),
        )
        items, truncated = await _drain(paginator, limit=limit)
        return {
            "spans": [_dump(s) for s in items],
            "count": len(items),
            "truncated": truncated,
        }

    async def list_span_groups(
        self,
        *,
        workspace: str,
        filter: dict | None,
        group_by: str = "session_id",
        sort: str = "-span_count",
        limit: int,
        since: datetime | None = None,
        evaluation_id: str | None = None,
    ) -> dict:
        """Group matching spans server-side and return the group rows.

        Each row is ``{"group": {<by-field>: value, ...}, "span_count": int}``.
        Grouping by ``session_id`` recovers the AUT's distinct sessions (its
        "traces") in a single request, so a wide survey fans out across many
        sessions instead of burning the budget on the spans of a few. ``total``
        is the server's full group count; ``truncated`` means more groups
        matched than were returned on this page.
        """
        effective_filter = _merge_eval_filter(_merge_since_filter(filter, since=since), evaluation_id=evaluation_id)
        page_size = max(1, min(limit, 1000))
        page = await self.client.intake.spans.groups.list(
            workspace=workspace,
            by=group_by,
            page=1,
            page_size=page_size,
            filter=cast(Any, effective_filter or omit),
            sort=cast(Any, sort),
        )
        groups = [_dump(g) for g in page.data]
        total = page.pagination.total_results if page.pagination is not None else len(groups)
        return {
            "groups": groups,
            "grouped_by": group_by,
            "count": len(groups),
            "total": total,
            "truncated": total > len(groups),
        }

    async def list_annotations(
        self,
        *,
        workspace: str,
        filter: dict | None,
        sort: str,
        limit: int,
        since: datetime | None = None,
    ) -> dict:
        effective_filter = _merge_created_since_filter(filter, since=since)
        paginator = self.client.intake.annotations.list(
            workspace=workspace,
            page_size=_page_size_for(limit),
            sort=cast(Any, sort),
            filter=cast(Any, effective_filter) or omit,
        )
        items, truncated = await _drain(paginator, limit=limit)
        return {
            "annotations": [_dump(a) for a in items],
            "count": len(items),
            "truncated": truncated,
        }

    async def get_span(self, *, workspace: str, span_id: str) -> dict:
        span = await self.client.intake.spans.retrieve(span_id, workspace=workspace)
        return _dump(span)

    async def get_annotation(self, *, workspace: str, annotation_id: str) -> dict:
        annotation = await self.client.intake.annotations.retrieve(annotation_id, workspace=workspace)
        return _dump(annotation)

    async def list_scores(self, *, workspace: str, span_id: str) -> dict:
        results = await self.client.intake.spans.evaluator_results.list(span_id, workspace=workspace)
        return {
            "evaluator_results": [_dump(r) for r in results],
            "count": len(results),
        }

    # -- insight read + result persistence: varies by backend ------------- #

    @abstractmethod
    async def list_insights(
        self,
        *,
        workspace: str,
        page: int,
        page_size: int,
        agent: str | None,
        status: InsightStatus | None,
    ) -> InsightPage:
        """List existing insights so the analyst can dedupe its findings.

        The remote backend lists from the Insights plugin API; the local
        backend lists from its YAML file, since the target deployment may not
        have the plugin installed.
        """
        ...

    @abstractmethod
    async def persist_result(self, *, workspace: str, agent: str, result: AnalystResult) -> str:
        """Persist the analyst's whole change-set and return a printable report.

        The shape on disk/in the store is the backend's concern; callers hand
        over the storage-agnostic :class:`AnalystResult` and get back the text
        the CLI prints (the model's summary followed by a line-item log).
        """
        ...


class RemoteAnalystBackend(AnalystBackend):
    """Persist insights via the Insights plugin API.

    Translates the SDK's HTTP 404 on an update into the backend-neutral
    not-found error so the persistence logic doesn't depend on ``httpx``
    semantics.
    """

    @property
    def _insights(self):
        return self.client.insights.insights

    async def list_insights(
        self,
        *,
        workspace: str,
        page: int,
        page_size: int,
        agent: str | None,
        status: InsightStatus | None,
    ) -> InsightPage:
        return await self._insights.list_insights(
            workspace=workspace,
            page=page,
            page_size=page_size,
            agent=agent,
            status=status,
        )

    async def persist_result(self, *, workspace: str, agent: str, result: AnalystResult) -> str:
        """Replay the change-set: insights into the DB.

        New insights are created with their evidence; the store auto-assigns a
        unique slug name and an id. Existing insights are referenced by id —
        only trace refs are appended.
        """
        lines: list[str] = []

        for new in result.new_insights:
            created = await self._create(
                workspace=workspace,
                title=new.title,
                agent=agent,
                description=new.description,
                status=new.status,
                trace_refs=new.trace_refs or None,
            )
            lines.append(f"- created: {new.title} [{created.id}] ({len(new.trace_refs)} trace refs)")

        for upd in result.updated_insights:
            try:
                if upd.trace_refs:
                    await self._add_trace_refs(
                        workspace=workspace,
                        insight_id=upd.id,
                        trace_refs=upd.trace_refs,
                    )
                else:
                    await self._get(workspace=workspace, insight_id=upd.id)
            except InsightNotFoundError:
                lines.append(f"- skipped (insight not found): {upd.id}")
                continue
            lines.append(f"- updated: {upd.id} ({len(upd.trace_refs)} trace refs)")

        if not lines:
            lines.append("- no insights created or updated")

        return f"{result.summary}\n\n" + "\n".join(lines)

    async def _create(
        self,
        *,
        workspace: str,
        title: str,
        agent: str,
        description: str,
        status: InsightStatus,
        trace_refs: list[str] | None,
    ) -> Insight:
        return await self._insights.create(
            workspace=workspace,
            title=title,
            agent=agent,
            description=description,
            status=status,
            trace_refs=_union_refs(None, trace_refs),
        )

    async def _add_trace_refs(self, *, workspace: str, insight_id: str, trace_refs: list[str]) -> Insight:
        current = await self._get(workspace=workspace, insight_id=insight_id)
        try:
            return await self._insights.update(
                workspace=workspace,
                insight_id=insight_id,
                trace_refs=_union_refs(current.trace_refs, trace_refs),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise InsightNotFoundError(insight_id) from exc
            raise

    async def _get(self, *, workspace: str, insight_id: str) -> Insight:
        try:
            return await self._insights.get(workspace=workspace, insight_id=insight_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise InsightNotFoundError(insight_id) from exc
            raise


def _generate_local_insight_id() -> str:
    """Mint a path-safe, unique insight id for offline mode.

    Mirrors the remote store's ``insight-<suffix>`` shape so file records look
    like what the platform would assign; the suffix is a uuid4 hex rather than
    the store's base58 encoding (no extra dependency), which is still unique.
    """
    return f"insight-{uuid.uuid4().hex}"


def _record_to_insight(record: dict) -> Insight:
    """Rebuild an :class:`Insight` (id/timestamps included) from a file record.

    A record is an :class:`Insight` JSON-able dump; any keys not on the entity
    are ignored by Pydantic during validation.
    """
    insight = Insight.model_validate(record)
    insight._id = record.get("id") or None
    for attr, key in (("_created_at", "created_at"), ("_updated_at", "updated_at")):
        raw = record.get(key)
        setattr(insight, attr, datetime.fromisoformat(raw) if raw else None)
    return insight


class LocalAnalystBackend(AnalystBackend):
    """Persist the analyst's result to a local YAML file (offline mode).

    For running against a deployment that hosts observability data but does not
    have the Insights plugin installed: reads of traces/spans/annotations still
    hit the live platform, but insights are both listed from and written to the
    file. The file accumulates across runs — ``persist_result`` merges the new
    change-set into whatever the file already holds rather than overwriting it,
    so re-running the analyst against the same file folds new evidence into
    existing insights instead of dropping prior work.

    File shape: ``{"insights": [<Insight record>, ...]}`` — each record is the
    stored entity.
    """

    def __init__(self, *, client: AsyncNeMoPlatform, path: Path) -> None:
        super().__init__(client)
        self.path = path

    def _read_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return list(raw.get("insights", []))

    def _write_records(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else None
        if not isinstance(document, dict):
            document = {}
        document["insights"] = records
        self.path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    async def persist_result(self, *, workspace: str, agent: str, result: AnalystResult) -> str:
        records = self._read_records()
        by_id = {(r.get("workspace"), r.get("id")): r for r in records}
        now = datetime.now(timezone.utc).isoformat()
        lines: list[str] = []

        for new in result.new_insights:
            insight_id = _generate_local_insight_id()
            record = {
                "id": insight_id,
                "workspace": workspace,
                "title": new.title,
                "agent": agent,
                "description": new.description,
                "status": new.status.value,
                "trace_refs": list(new.trace_refs),
                "created_at": now,
                "updated_at": now,
            }
            records.append(record)
            by_id[(workspace, insight_id)] = record
            lines.append(f"- created: {new.title} [{insight_id}] ({len(new.trace_refs)} trace refs)")

        for upd in result.updated_insights:
            existing = by_id.get((workspace, upd.id))
            if existing is None:
                lines.append(f"- skipped (insight not found): {upd.id}")
                continue
            existing["trace_refs"] = _union_refs(existing.get("trace_refs"), upd.trace_refs)
            existing["updated_at"] = now
            lines.append(f"- updated: {upd.id} ({len(upd.trace_refs)} trace refs)")

        if not lines:
            lines.append("- no insights created or updated")

        self._write_records(records)
        return f"{result.summary}\n\nWrote analyst result to {self.path}\n" + "\n".join(lines)

    async def list_insights(
        self,
        *,
        workspace: str,
        page: int,
        page_size: int,
        agent: str | None,
        status: InsightStatus | None,
    ) -> InsightPage:
        items = [_record_to_insight(r) for r in self._read_records() if r.get("workspace") == workspace]
        if agent:
            items = [i for i in items if i.agent == agent]
        if status is not None:
            items = [i for i in items if i.status == status]
        epoch = datetime.min.replace(tzinfo=timezone.utc)
        items.sort(key=lambda i: i.created_at or epoch, reverse=True)

        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        pagination = PaginationData(
            page=page,
            page_size=page_size,
            current_page_size=len(page_items),
            total_pages=max(1, (total + page_size - 1) // page_size) if page_size else 1,
            total_results=total,
        )
        return InsightPage(data=page_items, pagination=pagination)


def make_analyst_backend(*, client: AsyncNeMoPlatform, insights_output: str | None) -> AnalystBackend:
    """Select the analyst backend based on *insights_output*.

    When set, the analyst's result is written to that local YAML file (offline
    mode); otherwise the Insights plugin API and platform filesets on *client*
    are used. Reads always go through *client* either way.
    """
    if insights_output:
        return LocalAnalystBackend(client=client, path=Path(insights_output))
    return RemoteAnalystBackend(client)
