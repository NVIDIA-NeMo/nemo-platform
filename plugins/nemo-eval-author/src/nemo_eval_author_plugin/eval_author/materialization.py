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
from uuid import uuid4

import tomlkit
from harbor.models.task.task import Task as HarborTask
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import Task, local_path_from_uri

_MANIFEST_SCHEMA_VERSION = 3
_CONTENT_HASH_SCHEMA_VERSION = 1
_METRIC_CONTRACT_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ENVELOPE_DESCRIPTOR_FILENAME = ".nemo-trusted-harbor-envelope.json"
_ENVELOPE_POLICY_FILENAME = "nemo-task-envelope.json"


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


def _contains(parent: str, child: str) -> bool:
    parent_path = Path(parent)
    child_path = Path(child)
    return child_path == parent_path or parent_path in child_path.parents


@dataclass(frozen=True, slots=True)
class _MutationPolicy:
    task_data_paths: tuple[str, ...]
    verifier_paths: tuple[str, ...]


def _mutation_policy(task_dir: Path) -> _MutationPolicy | None:
    """Load the trusted-envelope policy without importing Experimentalist helpers."""
    descriptor = task_dir / _ENVELOPE_DESCRIPTOR_FILENAME
    if not descriptor.is_file():
        return None
    policy_path = task_dir / _ENVELOPE_POLICY_FILENAME
    if not policy_path.is_file():
        raise ValueError(f"Trusted Eval Author task is missing {_ENVELOPE_POLICY_FILENAME}: {task_dir}")
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid trusted task mutation policy {policy_path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported trusted task mutation policy version in {policy_path}")

    def paths_from_values(raw: object, key: str) -> tuple[str, ...]:
        if not isinstance(raw, list):
            raise ValueError(f"Trusted task mutation policy {key} must be a list of paths: {policy_path}")
        normalized: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item:
                raise ValueError(f"Trusted task mutation policy {key} must be a list of paths: {policy_path}")
            path = Path(item)
            if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
                raise ValueError(f"Unsafe trusted task mutation path {item!r}: {policy_path}")
            normalized.append(path.as_posix())
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"Duplicate trusted task mutation paths in {policy_path}")
        return tuple(normalized)

    def paths(key: str) -> tuple[str, ...]:
        return paths_from_values(payload.get(key, []), key)

    raw_task_data = payload.get("task_data", [])
    if not isinstance(raw_task_data, list):
        raise ValueError(f"Trusted task mutation policy task_data must be a list: {policy_path}")
    task_data_paths: list[str] = []
    for slot in raw_task_data:
        if not isinstance(slot, dict) or not isinstance(slot.get("path"), str):
            raise ValueError(f"Trusted task mutation policy task_data contains an invalid slot: {policy_path}")
        task_data_paths.extend(paths_from_values([slot["path"]], "task_data"))
    return _MutationPolicy(
        task_data_paths=tuple(task_data_paths),
        verifier_paths=paths("verifier_paths"),
    )


def _immutable_snapshot(task_dir: Path, *, mutable_paths: tuple[str, ...]) -> dict[str, str]:
    return {
        relative: digest
        for relative, digest in _file_hashes(task_dir).items()
        if not any(_contains(mutable, relative) for mutable in mutable_paths)
    }


def _assert_snapshot(
    task_dir: Path,
    *,
    mutable_paths: tuple[str, ...],
    expected: dict[str, str],
    phase: str,
) -> None:
    actual = _immutable_snapshot(task_dir, mutable_paths=mutable_paths)
    if actual == expected:
        return
    changed = sorted(path for path in set(expected) | set(actual) if expected.get(path) != actual.get(path))
    raise ValueError(
        f"Eval Author {phase} modified trusted task paths outside its envelope slots: " + ", ".join(changed[:20])
    )


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


@dataclass(frozen=True, slots=True)
class StagedInsightTask:
    """One copied task template waiting to be filled and validated."""

    index: int
    trace_ref: str
    slug: str
    path: Path
    task: Task
    mutation_policy: _MutationPolicy | None
    immutable_before_fill: dict[str, str] | None


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
            policy = _mutation_policy(task_dir)
            staged.append(
                StagedInsightTask(
                    index=index,
                    trace_ref=trace_ref,
                    slug=slug,
                    path=task_dir,
                    task=task,
                    mutation_policy=policy,
                    immutable_before_fill=(
                        _immutable_snapshot(task_dir, mutable_paths=policy.task_data_paths)
                        if policy is not None
                        else None
                    ),
                )
            )
        return staged

    def validate_fill_mutations(self, staged: StagedInsightTask) -> None:
        """Reject coding-agent edits outside declared trace-data slots."""
        if staged.mutation_policy is None or staged.immutable_before_fill is None:
            return
        _assert_snapshot(
            staged.path,
            mutable_paths=staged.mutation_policy.task_data_paths,
            expected=staged.immutable_before_fill,
            phase="template filling",
        )

    def metric_mutation_snapshot(self) -> dict[str, tuple[tuple[str, ...], dict[str, str]]]:
        """Capture non-verifier content before metric authoring begins."""
        snapshot: dict[str, tuple[tuple[str, ...], dict[str, str]]] = {}
        for task_dir in sorted(path for path in self.suite_dir.iterdir() if path.is_dir()):
            policy = _mutation_policy(task_dir)
            if policy is None:
                continue
            snapshot[task_dir.name] = (
                policy.verifier_paths,
                _immutable_snapshot(task_dir, mutable_paths=policy.verifier_paths),
            )
        return snapshot

    def validate_metric_mutations(
        self,
        snapshot: dict[str, tuple[tuple[str, ...], dict[str, str]]],
    ) -> None:
        """Reject metric-author edits outside declared verifier slots."""
        for task_name, (mutable_paths, expected) in snapshot.items():
            _assert_snapshot(
                self.suite_dir / task_name,
                mutable_paths=mutable_paths,
                expected=expected,
                phase="metric authoring",
            )

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
        pending_path = manifest_path.with_suffix(".json.pending")
        pending_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(pending_path, manifest_path)

        dataset = HarborDataset.from_path(
            self.suite_dir,
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
                "insight_suite_task_hashes": task_hashes,
            }
        )
        return FinalizedInsightSuite(
            identity=suite_identity,
            scorer_identity=scorer_identity,
            path=self.suite_dir,
            dataset=dataset,
        )
