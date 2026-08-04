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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import tomlkit
from harbor.models.task.task import Task as HarborTask
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import Task, local_path_from_uri

_MANIFEST_SCHEMA_VERSION = 3
_CONTENT_HASH_SCHEMA_VERSION = 1
_METRIC_CONTRACT_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Directory names for the two halves. Experimentalist declares the same names in its
# holdout_utils to decide which half to hide; they are duplicated rather than imported
# to keep Eval Author's dependency on Experimentalist shrinking, and pinned together by
# test_insight_split_names_match_eval_author in the Experimentalist suite.
INSIGHT_TRAIN_SPLIT = "insight-train"
INSIGHT_VALIDATION_SPLIT = "insight-validation"


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


def _scoring_dir(task_dir: Path) -> Path:
    """Return the directory whose contents decide which metrics a task emits.

    Falls back to the whole task directory for datasets that do not follow Harbor's
    verifier layout. A coarser hash still detects a task nobody touched, which is all
    :func:`verifier_hashes` needs.
    """
    try:
        return _verifier_dir(task_dir)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return task_dir


def verifier_hashes(tasks: Iterable[Task]) -> dict[str, str]:
    """Return each task's verifier content hash, keyed by task id.

    Snapshot this before metric authoring and compare after: a verifier whose hash did
    not move cannot have gained a metric key, so the comparison names exactly the tasks
    authoring skipped without needing to know the metric's name.

    Tasks with no readable files on disk are omitted rather than hashed as empty. A task
    this cannot inspect is not evidence that nobody authored it, and hashing them all to
    the same empty digest would accuse every one of them.
    """
    hashes: dict[str, str] = {}
    for task in tasks:
        if not task.uri:
            continue
        try:
            task_dir = local_path_from_uri(task.uri, context="Authored task").resolve()
        except ValueError:
            continue
        files = _file_hashes(_scoring_dir(task_dir))
        if files:
            hashes[task.id] = f"sha256:{_canonical_digest(files)}"
    return hashes


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
        task_metadata = {
            key: value for key, value in task_entry.items() if key not in {"content_hash", "files", "verifier"}
        }
        tasks.append(
            {
                **task_metadata,
                "content_hash": content_hash,
                "verifier": {
                    "path": verifier_path,
                    "content_hash": verifier_hash,
                },
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


def _write_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    """Write a suite manifest atomically."""
    pending_path = manifest_path.with_suffix(".json.pending")
    pending_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending_path, manifest_path)


def _task_hashes(tasks: list[dict[str, object]]) -> dict[str, dict[str, str]]:
    """Return per-task content and verifier hashes keyed by relative task path."""
    task_hashes: dict[str, dict[str, str]] = {}
    for task in tasks:
        task_path = task.get("path")
        content_hash = task.get("content_hash")
        verifier = task.get("verifier")
        verifier_hash = verifier.get("content_hash") if isinstance(verifier, dict) else None
        if not isinstance(task_path, str) or not isinstance(content_hash, str) or not isinstance(verifier_hash, str):
            raise ValueError(f"Finalized Insight suite has invalid task provenance: {task!r}")
        task_hashes[task_path] = {
            "content_hash": content_hash,
            "verifier_hash": verifier_hash,
        }
    return task_hashes


@dataclass(frozen=True, slots=True)
class StagedInsightTask:
    """One copied task template waiting to be filled and validated."""

    index: int
    trace_ref: str
    slug: str
    path: Path
    task: Task


@dataclass(frozen=True, slots=True)
class FinalizedInsightSuite:
    """Experiment-local Insight suite with deterministic content identities."""

    identity: str
    scorer_identity: str
    path: Path
    dataset: HarborDataset


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
        _write_manifest(manifest_path, manifest)

    def finalize(self) -> FinalizedInsightSuite:
        """Persist content identities on the experiment-local authored suite."""
        manifest_path = self.suite_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tasks, scorer_identity, suite_identity = _content_provenance(self.suite_dir, manifest)
        digest = suite_identity.removeprefix("sha256:")
        manifest.pop("artifact", None)
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
                "tasks": tasks,
            }
        )
        _write_manifest(manifest_path, manifest)

        dataset = HarborDataset.from_path(
            self.suite_dir,
            dataset_id=f"insight-{digest[:12]}",
        )
        dataset.metadata.update(
            {
                "insight_suite_identity": suite_identity,
                "insight_suite_scorer_identity": scorer_identity,
                "insight_suite_task_hashes": _task_hashes(tasks),
            }
        )
        return FinalizedInsightSuite(
            identity=suite_identity,
            scorer_identity=scorer_identity,
            path=self.suite_dir,
            dataset=dataset,
        )


@dataclass(frozen=True, slots=True)
class InsightSuiteSplit:
    """Train and validation halves materialized from one finalized Insight suite."""

    train: FinalizedInsightSuite | None
    validation: FinalizedInsightSuite | None


def split_insight_task_paths(task_paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Alternate task paths into train and validation, giving the odd task to train.

    Alternating instead of cutting the ordered list in half keeps any ordering bias
    in the source traces (recency, severity) spread across both halves.
    """
    return list(task_paths[0::2]), list(task_paths[1::2])


def _materialize_half(
    *,
    source_dir: Path,
    manifest: dict[str, object],
    task_paths: list[str],
    destination: Path,
    split: str,
) -> FinalizedInsightSuite | None:
    """Copy one half's tasks to ``destination`` and stamp its own content identity."""
    if not task_paths:
        return None

    raw_tasks = manifest.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Insight suite manifest has invalid tasks: {source_dir / 'manifest.json'}")
    entries_by_path: dict[str, dict[str, object]] = {}
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue
        task_entry = cast(dict[str, object], raw_task)
        relative_path = task_entry.get("path")
        if isinstance(relative_path, str):
            entries_by_path[relative_path] = task_entry
    if missing := [path for path in task_paths if path not in entries_by_path]:
        raise ValueError(f"Insight suite split references unknown tasks: {missing}")
    selected = [entries_by_path[path] for path in task_paths]

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    for relative_path in task_paths:
        shutil.copytree(source_dir / relative_path, destination / relative_path)

    half_manifest: dict[str, object] = {**manifest, "split": split, "tasks": selected}
    tasks, scorer_identity, suite_identity = _content_provenance(destination, half_manifest)
    digest = suite_identity.removeprefix("sha256:")
    half_manifest.update(
        {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "content_hash_schema_version": _CONTENT_HASH_SCHEMA_VERSION,
            "metric_contract_version": _METRIC_CONTRACT_VERSION,
            "suite_identity": suite_identity,
            "scorer": {
                "identity": scorer_identity,
                "metric_contract_version": _METRIC_CONTRACT_VERSION,
            },
            "tasks": tasks,
        }
    )
    _write_manifest(destination / "manifest.json", half_manifest)

    dataset = HarborDataset.from_path(destination, dataset_id=f"{split}-{digest[:12]}")
    dataset.metadata.update(
        {
            "insight_suite_identity": suite_identity,
            "insight_suite_scorer_identity": scorer_identity,
            "insight_suite_task_hashes": _task_hashes(tasks),
        }
    )
    return FinalizedInsightSuite(
        identity=suite_identity,
        scorer_identity=scorer_identity,
        path=destination,
        dataset=dataset,
    )


def materialize_insight_split(
    finalized: FinalizedInsightSuite,
    *,
    train_dir: Path,
    validation_dir: Path,
) -> InsightSuiteSplit:
    """Materialize a finalized suite into two physically separate halves.

    Physical separation is required because holdout relocates whole directories; a
    logical subset view would leave both halves interleaved in one directory where
    the validation half could not be hidden from the optimizing agent.

    Either half is ``None`` when the split assigns it no tasks, which happens for
    the validation half of a single-task suite.
    """
    manifest = json.loads((finalized.path / "manifest.json").read_text(encoding="utf-8"))
    task_paths = [task.id for task in finalized.dataset.list_tasks()]
    train_paths, validation_paths = split_insight_task_paths(task_paths)
    return InsightSuiteSplit(
        train=_materialize_half(
            source_dir=finalized.path,
            manifest=manifest,
            task_paths=train_paths,
            destination=train_dir,
            split=INSIGHT_TRAIN_SPLIT,
        ),
        validation=_materialize_half(
            source_dir=finalized.path,
            manifest=manifest,
            task_paths=validation_paths,
            destination=validation_dir,
            split=INSIGHT_VALIDATION_SPLIT,
        ),
    )
