# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insight storage backend for the analyst's final change-set.

Trace reads are supplied separately through the shared ``TraceProvider``
contract. This backend owns only Insight listing and result persistence.

Insights always go to the platform. :class:`RemoteAnalystBackend` lists them via
the plugin API and persists the result as Insight rows through it. Given an
:class:`InsightsFileStore`, it then mirrors what the platform stored — platform
ids included — into a local YAML file (``--insights-file-output``), so the two
stores speak the same identifiers and a later run's updates land in both. The
platform is the source of truth: it is written first and the file follows, and a
file that cannot be written degrades to a warning on the run report rather than
failing a run whose platform writes already succeeded.

:class:`LocalAnalystBackend` never touches the plugin API, listing from and
persisting to the file alone. It is **maintainer tooling, not a user-facing
mode**. There is no CLI flag for it; only ``make_analyst_backend``'s
``local_only`` argument selects it.

:func:`make_analyst_backend` picks one. The client's lifecycle is owned by the
caller (the CLI), so the backend never closes it.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from nemo_insights_plugin.analyst.result import AnalystResult
from nemo_insights_plugin.entities import Insight, InsightStatus
from nemo_insights_plugin.schema import InsightListItem, InsightPage
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.schema import PaginationData


class InsightNotFoundError(Exception):
    """No insight with the given id exists in the workspace."""


def _union_refs(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """Append *new* refs to *existing*, de-duplicating and preserving order."""
    merged = list(existing or [])
    seen = set(merged)
    for ref in new or []:
        if ref not in seen:
            merged.append(ref)
            seen.add(ref)
    return merged


class AnalystBackend(ABC):
    """Pluggable Insight listing and result persistence."""

    def __init__(self, client: AsyncNeMoPlatform) -> None:
        self.client = client

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


def _to_list_item(insight: Insight) -> InsightListItem:
    """Convert an Insight without dropping its private entity metadata."""
    item = InsightListItem.model_validate(insight.model_dump(exclude_computed_fields=True))
    if insight.__pydantic_private__ is not None:
        item.__pydantic_private__ = insight.__pydantic_private__.copy()
    return item


def _insight_to_record(insight: Insight, *, workspace: str) -> dict:
    """Flatten a stored :class:`Insight` into a file record.

    Keeps the platform's id and timestamps rather than minting local ones: the
    mirror is only useful if its records can be matched against the platform
    rows they came from on the next run.
    """
    return {
        "id": insight.id,
        "workspace": workspace,
        "name": insight.name,
        "title": insight.title,
        "agent": insight.agent,
        "description": insight.description,
        "status": insight.status.value,
        "trace_refs": list(insight.trace_refs),
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "updated_at": insight.updated_at.isoformat() if insight.updated_at else None,
    }


class InsightsFileStore:
    """The local Insights YAML document: ``{"insights": [<record>, ...]}``.

    Shared by the local backend (as its store) and the remote backend (as its
    mirror). Writes preserve any other top-level keys the document carries, so
    a hand-maintained file keeps its own metadata across analyst runs.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def read_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return list(raw.get("insights", []))

    def write_records(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else None
        if not isinstance(document, dict):
            document = {}
        document["insights"] = records
        self.path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def merge(self, records: list[dict]) -> None:
        """Upsert *records* by ``(workspace, id)`` into the existing document."""
        existing = self.read_records()
        index = {(r.get("workspace"), r.get("id")): position for position, r in enumerate(existing)}
        for record in records:
            key = (record.get("workspace"), record.get("id"))
            position = index.get(key)
            if position is None:
                index[key] = len(existing)
                existing.append(record)
            else:
                existing[position] = record
        self.write_records(existing)


class RemoteAnalystBackend(AnalystBackend):
    """Persist insights via the Insights plugin API, optionally mirroring to a file.

    Translates the SDK's HTTP 404 on an update into the backend-neutral
    not-found error so the persistence logic doesn't depend on ``httpx``
    semantics.
    """

    def __init__(self, client: AsyncNeMoPlatform, mirror: InsightsFileStore | None = None) -> None:
        super().__init__(client)
        self.mirror = mirror

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
        """Replay the change-set: insights into the DB, then into the mirror.

        New insights are created with their evidence; the store auto-assigns a
        unique slug name and an id. Existing insights are referenced by id —
        only trace refs are appended. Whatever the platform stored is then
        mirrored to the local file, if one is configured.
        """
        lines: list[str] = []
        stored: list[Insight] = []

        for new in result.new_insights:
            created = await self._create(
                workspace=workspace,
                title=new.title,
                agent=agent,
                description=new.description,
                status=new.status,
                trace_refs=new.trace_refs or None,
            )
            stored.append(created)
            lines.append(f"- created: {new.title} [{created.id}] ({len(new.trace_refs)} trace refs)")

        for upd in result.updated_insights:
            try:
                if upd.trace_refs:
                    updated = await self._add_trace_refs(
                        workspace=workspace,
                        insight_id=upd.id,
                        trace_refs=upd.trace_refs,
                    )
                else:
                    updated = await self._get(workspace=workspace, insight_id=upd.id)
            except InsightNotFoundError:
                lines.append(f"- skipped (insight not found): {upd.id}")
                continue
            stored.append(updated)
            lines.append(f"- updated: {upd.id} ({len(upd.trace_refs)} trace refs)")

        if not lines:
            lines.append("- no insights created or updated")

        lines.extend(self._mirror(workspace=workspace, stored=stored))
        return f"{result.summary}\n\n" + "\n".join(lines)

    def _mirror(self, *, workspace: str, stored: list[Insight]) -> list[str]:
        """Write what the platform stored to the mirror file; report the outcome.

        The platform writes have already landed by the time this runs, so a
        file that cannot be written is reported as a warning instead of raising
        — failing here would claim the whole run failed when the source of
        truth is up to date.
        """
        if self.mirror is None:
            return []
        try:
            self.mirror.merge([_insight_to_record(insight, workspace=workspace) for insight in stored])
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            detail = " ".join(str(exc).split())
            return [f"- warning: platform updated, but mirror {self.mirror.path} could not be written: {detail}"]
        return [f"- mirrored {len(stored)} insight(s) to {self.mirror.path}"]

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


class LocalAnalystBackend(AnalystBackend):
    """Persist the analyst's result to a local YAML file only.

    Maintainer tooling for the insights evaluation, not a user-facing mode — no CLI
    flag reaches it. The evaluation treats the YAML as the artifact under test
    (checked in, hashed, diffed across runs) and may analyze subjects without
    the Insights plugin, so its runs must neither require nor touch platform
    Insight rows.

    Insights are both listed from and written to the file. Ids are minted locally, so a
    file written this way is an independent store rather than a mirror of
    platform rows.

    The file accumulates across runs — ``persist_result`` merges the new
    change-set into whatever the file already holds rather than overwriting it,
    so re-running the analyst against the same file folds new evidence into
    existing insights instead of dropping prior work.

    File shape: ``{"insights": [<Insight record>, ...]}`` — each record is the
    stored entity.
    """

    def __init__(self, *, client: AsyncNeMoPlatform, path: Path) -> None:
        super().__init__(client)
        self.store = InsightsFileStore(path)

    @property
    def path(self) -> Path:
        return self.store.path

    async def persist_result(self, *, workspace: str, agent: str, result: AnalystResult) -> str:
        records = self.store.read_records()
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

        self.store.write_records(records)
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
        items = [
            _to_list_item(_record_to_insight(r)) for r in self.store.read_records() if r.get("workspace") == workspace
        ]
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


def make_analyst_backend(
    *,
    client: AsyncNeMoPlatform,
    insights_output: str | None,
    local_only: bool = False,
) -> AnalystBackend:
    """Select the analyst backend.

    Results are written through the Insights plugin API on *client*, and
    *insights_output* (when set) additionally receives a mirror of what the
    platform stored. *local_only* is reserved for the insights evaluation: it skips
    the platform and makes *insights_output* the sole store, so a path is
    required. No CLI flag sets it.
    """
    if local_only:
        if not insights_output:
            raise ValueError("local-only analysis requires an insights output path")
        return LocalAnalystBackend(client=client, path=Path(insights_output))
    mirror = InsightsFileStore(Path(insights_output)) if insights_output else None
    return RemoteAnalystBackend(client, mirror=mirror)
