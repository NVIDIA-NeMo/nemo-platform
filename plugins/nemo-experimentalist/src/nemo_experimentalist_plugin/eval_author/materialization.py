# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic persistence for Eval Author-built Harbor insight suites."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4

import tomlkit
from harbor.models.task.task import Task as HarborTask
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import Task, local_path_from_uri

_MANIFEST_SCHEMA_VERSION = 2
_CONTENT_HASH_SCHEMA_VERSION = 1
_METRIC_CONTRACT_VERSION = 1
_ARTIFACT_SCHEME = "nemo-experimentalist-insight-suite"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _slug(value: str, *, fallback: str, max_length: int = 48) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")[:max_length].rstrip("-")
    return slug or fallback


def _digest(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256_bytes(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _verifier_dir(task_dir: Path) -> Path:
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    verifier = config.get("verifier")
    if isinstance(verifier, dict):
        configured = verifier.get("directory")
        if isinstance(configured, str) and configured.strip():
            path = Path(configured)
            return path if path.is_absolute() else task_dir / path
    for name in ("tests", "test"):
        path = task_dir / name
        if path.is_dir():
            return path
    raise ValueError(f"Materialized task has no verifier directory: {task_dir}")


def _content_provenance(suite_dir: Path, manifest: dict[str, object]) -> tuple[list[dict[str, object]], str, str]:
    raw_tasks = manifest.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Insight suite manifest has invalid tasks: {suite_dir / 'manifest.json'}")

    tasks: list[dict[str, object]] = []
    scorer_inputs: list[dict[str, str]] = []
    suite_inputs: list[dict[str, str]] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            raise ValueError(f"Insight suite manifest has invalid task entry: {raw_task!r}")
        if not all(isinstance(key, str) for key in raw_task):
            raise ValueError(f"Insight suite manifest task has invalid keys: {raw_task!r}")
        task_entry = cast(dict[str, object], raw_task)
        relative_path = task_entry.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"Insight suite manifest task has invalid path: {relative_path!r}")
        task_dir = (suite_dir / relative_path).resolve()
        try:
            task_dir.relative_to(suite_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Insight suite manifest task escapes the suite: {relative_path!r}") from exc
        if not task_dir.is_dir():
            raise ValueError(f"Insight suite manifest task path is missing: {task_dir}")

        files = _file_hashes(task_dir)
        verifier_dir = _verifier_dir(task_dir).resolve()
        try:
            verifier_path = verifier_dir.relative_to(task_dir).as_posix()
        except ValueError as exc:
            raise ValueError(f"Insight suite verifier must be contained in its task: {verifier_dir}") from exc
        verifier_files = _file_hashes(verifier_dir)
        content_hash = f"sha256:{_canonical_digest(files)}"
        verifier_hash = f"sha256:{_canonical_digest(verifier_files)}"
        tasks.append(
            {
                **task_entry,
                "content_hash": content_hash,
                "verifier": {
                    "path": verifier_path,
                    "content_hash": verifier_hash,
                    "files": verifier_files,
                },
                "files": files,
            }
        )
        scorer_inputs.append({"path": relative_path, "verifier_hash": verifier_hash})
        suite_inputs.append(
            {
                "path": relative_path,
                "task_hash": content_hash,
                "verifier_hash": verifier_hash,
            }
        )

    scorer_identity = f"sha256:{_canonical_digest(scorer_inputs)}"
    suite_payload = {
        "schema_version": _CONTENT_HASH_SCHEMA_VERSION,
        "insight_id": manifest.get("insight_id"),
        "metric_contract_version": _METRIC_CONTRACT_VERSION,
        "scorer_identity": scorer_identity,
        "tasks": suite_inputs,
    }
    suite_identity = f"sha256:{_canonical_digest(suite_payload)}"
    return tasks, scorer_identity, suite_identity


@dataclass(frozen=True, slots=True)
class StagedInsightTask:
    """One copied task template waiting to be filled and validated."""

    index: int
    trace_ref: str
    slug: str
    path: Path
    task: Task


@dataclass(frozen=True, slots=True)
class InsightSuiteArtifact:
    """Immutable, content-addressed result of an authored Insight suite."""

    identity: str
    scorer_identity: str
    ref: str
    path: Path
    dataset: HarborDataset


def resolve_insight_suite_artifact(experiment_dir: Path, artifact_ref: str) -> Path:
    """Resolve and verify a portable Insight-suite artifact reference."""
    parsed = urlparse(artifact_ref)
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != _ARTIFACT_SCHEME
        or not parsed.netloc
        or len(parts) != 2
        or parts[0] != "sha256"
        or not _SHA256_RE.fullmatch(parts[1])
    ):
        raise ValueError(f"Invalid Insight suite artifact reference: {artifact_ref!r}")

    suite_dir = (
        experiment_dir.resolve()
        / "eval-and-optimize"
        / "eval_author"
        / parsed.netloc
        / "artifacts"
        / parts[1]
        / "insight-suite"
    )
    manifest_path = suite_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Insight suite artifact not found: {artifact_ref}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _, scorer_identity, suite_identity = _content_provenance(suite_dir, manifest)
    expected_identity = f"sha256:{parts[1]}"
    if manifest.get("suite_identity") != expected_identity or suite_identity != expected_identity:
        raise ValueError(f"Insight suite artifact content does not match reference: {artifact_ref}")
    scorer = manifest.get("scorer")
    if not isinstance(scorer, dict) or scorer.get("identity") != scorer_identity:
        raise ValueError(f"Insight suite scorer content does not match reference: {artifact_ref}")
    return suite_dir


class InsightSuite:
    """Build one experiment-local persisted Harbor dataset for an Insight."""

    def __init__(self, *, experiment_dir: Path, insight_id: str, task_template: Task) -> None:
        """Initialize deterministic paths and template provenance for a suite."""
        if not insight_id:
            raise ValueError("Insight id is required to materialize an insight suite")
        if not task_template.uri:
            raise ValueError("Task template URI is required to materialize an insight suite")

        self.experiment_dir = experiment_dir.resolve()
        self.insight_id = insight_id
        self.template_dir = local_path_from_uri(
            task_template.uri,
            context="Eval Author task template",
        ).resolve()
        if not self.template_dir.is_dir():
            raise ValueError(f"Eval Author task template is not a directory: {self.template_dir}")
        self.template_uri = self.template_dir.as_uri()
        insight_slug = f"{_slug(insight_id, fallback='insight')}-{_digest(insight_id)}"
        self.root = self.experiment_dir / "eval-and-optimize" / "eval_author" / insight_slug
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
        """Remove an unpromoted candidate suite and reset its staging state."""
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

    def finalize_artifact(self) -> InsightSuiteArtifact:
        """Freeze the authored suite under a verified content-addressed reference."""
        manifest_path = self.suite_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tasks, scorer_identity, suite_identity = _content_provenance(self.suite_dir, manifest)
        digest = suite_identity.removeprefix("sha256:")
        artifact_ref = f"{_ARTIFACT_SCHEME}://{self.root.name}/sha256/{digest}"
        artifact_path = self.root / "artifacts" / digest / "insight-suite"
        manifest.update(
            {
                "schema_version": _MANIFEST_SCHEMA_VERSION,
                "content_hash_schema_version": _CONTENT_HASH_SCHEMA_VERSION,
                "metric_contract_version": _METRIC_CONTRACT_VERSION,
                "suite_identity": suite_identity,
                "scorer": {
                    "identity": scorer_identity,
                    "metric_contract_version": _METRIC_CONTRACT_VERSION,
                },
                "artifact": {
                    "ref": artifact_ref,
                    "relative_path": artifact_path.relative_to(self.experiment_dir).as_posix(),
                },
                "tasks": tasks,
            }
        )
        pending_path = manifest_path.with_suffix(".json.pending")
        pending_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(pending_path, manifest_path)

        if artifact_path.exists():
            resolved = resolve_insight_suite_artifact(self.experiment_dir, artifact_ref)
            if resolved != artifact_path.resolve():
                raise ValueError(f"Insight suite artifact resolved to unexpected path: {resolved}")
        else:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_artifact = artifact_path.parent / f".candidate-{uuid4().hex}"
            shutil.copytree(self.suite_dir, candidate_artifact)
            try:
                os.replace(candidate_artifact, artifact_path)
            finally:
                if candidate_artifact.exists():
                    shutil.rmtree(candidate_artifact)

        dataset = HarborDataset.from_path(
            artifact_path,
            dataset_id=f"insight-{digest[:12]}",
        )
        task_hashes: dict[str, dict[str, str]] = {}
        for task in tasks:
            task_path = task.get("path")
            content_hash = task.get("content_hash")
            verifier = task.get("verifier")
            verifier_hash = verifier.get("content_hash") if isinstance(verifier, dict) else None
            if (
                not isinstance(task_path, str)
                or not isinstance(content_hash, str)
                or not isinstance(verifier_hash, str)
            ):
                raise ValueError(f"Finalized Insight suite has invalid task provenance: {task!r}")
            task_hashes[task_path] = {
                "content_hash": content_hash,
                "verifier_hash": verifier_hash,
            }
        dataset.metadata.update(
            {
                "insight_suite_identity": suite_identity,
                "insight_suite_scorer_identity": scorer_identity,
                "insight_suite_artifact_ref": artifact_ref,
                "insight_suite_task_hashes": task_hashes,
            }
        )
        return InsightSuiteArtifact(
            identity=suite_identity,
            scorer_identity=scorer_identity,
            ref=artifact_ref,
            path=artifact_path,
            dataset=dataset,
        )
