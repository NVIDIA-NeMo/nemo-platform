# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic persistence for Eval Author-built Harbor insight suites."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import tomlkit
from harbor.models.task.task import Task as HarborTask
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    Task,
    local_path_from_uri,
)
from nemo_platform import AsyncNeMoPlatform

_MANIFEST_SCHEMA_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str, *, fallback: str, max_length: int = 48) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")[:max_length].rstrip("-")
    return slug or fallback


def _digest(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True, slots=True)
class StagedInsightTask:
    """One copied task template waiting to be filled and validated."""

    index: int
    trace_ref: str
    slug: str
    path: Path
    task: Task


class InsightSuite:
    """Build and publish one persisted Harbor dataset for an Insight."""

    def __init__(self, *, experiment_dir: Path, insight_id: str, task_template: Task) -> None:
        """Initialize deterministic paths and template provenance for a suite."""
        if not insight_id:
            raise ValueError("Insight id is required to materialize an insight suite")
        if not task_template.uri:
            raise ValueError("Task template URI is required to materialize an insight suite")

        self.insight_id = insight_id
        self.template_dir = local_path_from_uri(
            task_template.uri,
            context="Eval Author task template",
        ).resolve()
        if not self.template_dir.is_dir():
            raise ValueError(f"Eval Author task template is not a directory: {self.template_dir}")
        self.template_uri = self.template_dir.as_uri()
        insight_slug = f"{_slug(insight_id, fallback='insight')}-{_digest(insight_id)}"
        self.root = experiment_dir.resolve() / "eval-and-optimize" / "eval_author" / insight_slug
        self.suite_dir = self.root / "insight-suite"
        self._candidate_root: Path | None = None
        self._candidate_suite: Path | None = None

    @staticmethod
    def task_slug(index: int, trace_ref: str) -> str:
        """Return a stable, collision-resistant directory name for one trace occurrence."""
        return f"{index:03d}-{_slug(trace_ref, fallback='trace')}-{_digest(trace_ref)}"

    def stage(self, trace_refs: list[str]) -> list[StagedInsightTask]:
        """Copy one template per trace into an isolated candidate suite."""
        if self._candidate_root is not None:
            raise RuntimeError("Insight suite staging has already started")
        self._candidate_root = self.root / "work" / f"candidate-{uuid4().hex}"
        self._candidate_suite = self._candidate_root / "insight-suite"
        self._candidate_suite.mkdir(parents=True)

        staged: list[StagedInsightTask] = []
        for index, trace_ref in enumerate(trace_refs, start=1):
            slug = self.task_slug(index, trace_ref)
            task_dir = self._candidate_suite / slug
            shutil.copytree(self.template_dir, task_dir)
            task = list(HarborDataset.from_path(task_dir).list_tasks())[0]
            staged.append(StagedInsightTask(index=index, trace_ref=trace_ref, slug=slug, path=task_dir, task=task))
        return staged

    def discard(self) -> None:
        """Remove an unpublished candidate suite and reset its staging state."""
        if self._candidate_root is not None and self._candidate_root.exists():
            shutil.rmtree(self._candidate_root)
        self._candidate_root = None
        self._candidate_suite = None

    def validate(self, staged: StagedInsightTask) -> None:
        """Stamp deterministic identity and provenance, then validate with Harbor."""
        toml_path = staged.path / "task.toml"
        document = tomlkit.parse(toml_path.read_text(encoding="utf-8"))
        task_table = document.get("task")
        if task_table is None:
            raise ValueError(f"Materialized task has no [task] table: {toml_path}")
        raw_name = task_table.get("name")
        if not isinstance(raw_name, str) or "/" not in raw_name:
            raise ValueError(f"Materialized task [task].name must use org/name format: {raw_name!r}")
        organization, short_name = raw_name.rsplit("/", 1)
        base_name = short_name.split("__", 1)[0]
        task_table["name"] = f"{organization}/{base_name}__{staged.slug}"

        metadata = document.get("metadata")
        if metadata is None:
            metadata = tomlkit.table()
            document["metadata"] = metadata
        provenance = metadata.get("nemo_experimentalist")
        if provenance is None:
            provenance = tomlkit.table()
            metadata["nemo_experimentalist"] = provenance
        provenance["source_trace_ref"] = staged.trace_ref
        provenance["insight_id"] = self.insight_id
        toml_path.write_text(tomlkit.dumps(document), encoding="utf-8")

        instruction_path = staged.path / "instruction.md"
        if not instruction_path.is_file() or not instruction_path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Materialized task instruction is missing or empty: {instruction_path}")
        for directory_name in ("environment", "tests"):
            directory = staged.path / directory_name
            if not directory.is_dir():
                raise ValueError(f"Materialized task is missing required {directory_name}/ directory: {directory}")
        HarborTask(staged.path)

    def promote_local(self, trace_refs: list[str], staged_tasks: list[StagedInsightTask]) -> HarborDataset:
        """Promote the validated candidate to the experiment-local working copy."""
        if self._candidate_root is None or self._candidate_suite is None:
            raise RuntimeError("Insight suite has not been staged")

        manifest = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "insight_id": self.insight_id,
            "trace_refs": trace_refs,
            "task_template": {"uri": self.template_uri},
            "tasks": [
                {
                    "index": task.index,
                    "path": task.slug,
                    "source_trace_ref": task.trace_ref,
                    "analysis": {"status": "pending"},
                }
                for task in staged_tasks
            ],
        }
        (self._candidate_suite / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        self.root.mkdir(parents=True, exist_ok=True)
        backup = self.root / f".insight-suite-backup-{uuid4().hex}"
        had_existing = self.suite_dir.exists()
        if had_existing:
            os.replace(self.suite_dir, backup)
        try:
            os.replace(self._candidate_suite, self.suite_dir)
            dataset = HarborDataset.from_path(
                self.suite_dir,
                dataset_id=f"insight-{_digest(self.insight_id, 12)}",
            )
            for task in dataset.list_tasks():
                HarborTask(local_path_from_uri(task.uri, context="Materialized Harbor task"))
        except BaseException as exc:
            try:
                if had_existing and backup.exists():
                    if self.suite_dir.exists():
                        shutil.rmtree(self.suite_dir)
                    os.replace(backup, self.suite_dir)
                elif self.suite_dir.exists():
                    shutil.rmtree(self.suite_dir)
                self.discard()
            except BaseException as rollback_exc:
                rollback_exc.add_note(f"Local Insight suite promotion also failed before rollback: {exc!r}")
                raise rollback_exc from exc
            raise

        if backup.exists():
            shutil.rmtree(backup)
        self.discard()
        return dataset

    def record_analysis(self, statuses: dict[str, tuple[str, str | None]]) -> None:
        """Persist per-task analysis outcomes without changing suite membership."""
        manifest_path = self.suite_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for task in manifest["tasks"]:
            status, error = statuses.get(task["path"], ("pending", None))
            task["analysis"] = {"status": status}
            if error is not None:
                task["analysis"]["error"] = error
        pending_path = manifest_path.with_suffix(".json.pending")
        pending_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(pending_path, manifest_path)

    async def publish_fileset(self, client: AsyncNeMoPlatform, workspace: str) -> DatasetRef:
        """Upload the complete local suite to a fresh NeMo Platform Fileset."""
        fileset_name = (
            f"nemo-experimentalist-insight-{_slug(self.insight_id, fallback='insight', max_length=80)}-{uuid4().hex}"
        )
        fileset = await client.files.filesets.create(
            workspace=workspace,
            name=fileset_name,
            description="Eval Author-built Harbor tasks materialized from Insight production traces.",
            purpose="dataset",
        )
        try:
            await client.files.upload(
                local_path=f"{self.suite_dir}{os.sep}",
                fileset=fileset.name,
                workspace=workspace,
            )
            local_files = {
                path.relative_to(self.suite_dir).as_posix(): path.stat().st_size
                for path in self.suite_dir.rglob("*")
                if path.is_file()
            }
            uploaded = await client.files.list(fileset=fileset.name, workspace=workspace)
            remote_files = {file.path: file.size for file in uploaded.data}
            if remote_files != local_files:
                raise RuntimeError(
                    f"Uploaded Insight suite Fileset {fileset.name!r} does not match the validated local suite"
                )
        except BaseException as exc:
            try:
                await client.files.filesets.delete(fileset.name, workspace=workspace)
            except BaseException as cleanup_exc:
                cleanup_exc.add_note(f"Fileset publication also failed before cleanup: {exc!r}")
                raise cleanup_exc from exc
            raise

        return DatasetRef(
            uri=f"fileset://{workspace}/{fileset.name}",
            description="Eval Author-built Harbor tasks materialized from Insight production traces.",
            metadata={
                "id": f"insight-{_digest(self.insight_id, 12)}",
                "insight_id": self.insight_id,
                "fileset_id": fileset.id,
                "fileset_name": fileset.name,
                "workspace": workspace,
            },
        )
