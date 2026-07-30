# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed, host-owned Harbor task envelopes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tomllib
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

import tomlkit
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef, local_path_from_uri
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENVELOPE_DESCRIPTOR_FILENAME = ".nemo-trusted-harbor-envelope.json"
ENVELOPE_POLICY_FILENAME = "nemo-task-envelope.json"
ENVELOPE_MANIFEST_FILENAME = "manifest.json"
ENVELOPE_SCHEMA_VERSION = 1
HARBOR_ENVELOPE_CATALOG_ENV = "NEMO_EXPERIMENTALIST_HARBOR_ENVELOPE_CATALOG"
_TRANSPORT_IGNORED_PARTS = frozenset({".git", ".venv", "__pycache__"})
_FORBIDDEN_OVERLAY_FILENAMES = frozenset(
    {
        ".dockerignore",
        "Containerfile",
        "Dockerfile",
        ENVELOPE_DESCRIPTOR_FILENAME,
        ENVELOPE_POLICY_FILENAME,
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "task.toml",
    }
)

EnvelopeId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Sha256Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
RelativePath = Annotated[str, Field(min_length=1, max_length=1024)]


def _validated_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"path must be a safe relative POSIX path: {value!r}")
    return path.as_posix()


class TaskDataSlot(BaseModel):
    """One exact, typed trace-data file that Eval Author may populate."""

    model_config = ConfigDict(extra="forbid")

    path: RelativePath
    media_type: Literal["application/json", "text/plain"]
    max_bytes: int = Field(ge=1, le=16 * 1024 * 1024)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validated_relative_path(value)


class TaskEnvelopePolicy(BaseModel):
    """Mutable slots intentionally exposed by one trusted task template."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = ENVELOPE_SCHEMA_VERSION
    task_data: list[TaskDataSlot] = Field(default_factory=list, max_length=128)
    verifier_paths: list[RelativePath] = Field(default_factory=list, max_length=32)

    @field_validator("verifier_paths")
    @classmethod
    def validate_paths(cls, value: list[str]) -> list[str]:
        normalized = [_validated_relative_path(item) for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("mutable paths must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def reject_overlapping_authorities(self) -> TaskEnvelopePolicy:
        task_paths = [PurePosixPath(slot.path) for slot in self.task_data]
        verifier_paths = [PurePosixPath(value) for value in self.verifier_paths]
        if len({slot.path for slot in self.task_data}) != len(self.task_data):
            raise ValueError("task-data paths must not contain duplicates")
        for task_path in task_paths:
            for verifier_path in verifier_paths:
                if _contains(task_path, verifier_path) or _contains(verifier_path, task_path):
                    raise ValueError(f"task-data and verifier paths must not overlap: {task_path} and {verifier_path}")
        return self

    @property
    def task_data_paths(self) -> list[str]:
        """Return exact trace-data file slots."""
        return [slot.path for slot in self.task_data]


class TrustedTaskManifest(BaseModel):
    """One immutable task and its declared overlay policy."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    path: str
    content_digest: Sha256Digest
    policy: TaskEnvelopePolicy = Field(default_factory=TaskEnvelopePolicy)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if value == ".":
            return value
        return _validated_relative_path(value)


class TrustedEnvelopeManifest(BaseModel):
    """Bridge-owned manifest for one registered Harbor dataset."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = ENVELOPE_SCHEMA_VERSION
    envelope_id: EnvelopeId
    envelope_digest: Sha256Digest
    source: str
    tasks: list[TrustedTaskManifest] = Field(min_length=1, max_length=4096)

    @field_validator("tasks")
    @classmethod
    def validate_unique_tasks(cls, value: list[TrustedTaskManifest]) -> list[TrustedTaskManifest]:
        ids = [task.task_id for task in value]
        paths = [task.path for task in value]
        if len(set(ids)) != len(ids):
            raise ValueError("envelope task ids must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("envelope task paths must be unique")
        return value


class TrustedEnvelopeDescriptor(BaseModel):
    """Untrusted-readable handle that binds local task paths to a host envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = ENVELOPE_SCHEMA_VERSION
    envelope_id: EnvelopeId
    envelope_digest: Sha256Digest
    tasks: list[TrustedTaskManifest] = Field(min_length=1, max_length=4096)


class EnvelopeTaskSelection(BaseModel):
    """One requested materialization from a registered base task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    base_task_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ResolvedEnvelopeTask(BaseModel):
    """Envelope binding and policy resolved for one sandbox-visible task."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    envelope_id: EnvelopeId
    envelope_digest: Sha256Digest
    task_id: str
    base_task_id: str
    task_path: Path
    policy: TaskEnvelopePolicy


class RegisteredEnvelope(BaseModel):
    """Host-side registration result used to forward trusted inputs."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    manifest: TrustedEnvelopeManifest
    dataset_path: Path


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _sha256_bytes(payload)


def _contains(parent: PurePosixPath, child: PurePosixPath) -> bool:
    return child == parent or parent in child.parents


def path_is_allowed(relative: str, allowed: Iterable[str]) -> bool:
    """Return whether *relative* is equal to or below one declared slot."""
    path = PurePosixPath(_validated_relative_path(relative))
    return any(_contains(PurePosixPath(value), path) for value in allowed)


def _tree_entries(
    root: Path,
    *,
    exclude: set[str] | None = None,
    ignored_parts: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    excluded = exclude or set()
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        if any(part in ignored_parts for part in PurePosixPath(relative).parts):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"Trusted envelope source contains a symbolic link: {relative}")
        if stat.S_ISDIR(mode):
            entries.append({"path": relative, "type": "directory"})
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"Trusted envelope source contains a special file: {relative}")
        entries.append(
            {
                "path": relative,
                "type": "file",
                "digest": _sha256_bytes(path.read_bytes()),
                "mode": oct(stat.S_IMODE(mode)),
            }
        )
    return entries


def tree_digest(root: Path, *, exclude: set[str] | None = None) -> str:
    """Hash paths, content, modes, and empty directories without following links."""
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Envelope tree not found: {source}")
    return _canonical_digest(_tree_entries(source, exclude=exclude))


def transport_tree_digest(root: Path) -> str:
    """Hash the files transported by ``create_directory_archive``."""
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Transport tree not found: {source}")
    return _canonical_digest(_tree_entries(source, ignored_parts=_TRANSPORT_IGNORED_PARTS))


def _safe_copy_tree(source: Path, destination: Path) -> None:
    """Copy a tree only after rejecting links and special files."""
    _tree_entries(source)
    shutil.copytree(source, destination, copy_function=shutil.copy2)


def _policy_for_task(task_dir: Path) -> TaskEnvelopePolicy:
    policy_path = task_dir / ENVELOPE_POLICY_FILENAME
    if not policy_path.is_file():
        return TaskEnvelopePolicy()
    try:
        policy = TaskEnvelopePolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Invalid task envelope policy {policy_path}: {exc}") from exc
    for slot in policy.task_data:
        path = task_dir / slot.path
        if path.exists() and not path.is_file():
            raise ValueError(f"Trusted task-data slot must name a file: {path}")
    return policy


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-")
    return normalized[:72] or "dataset"


def register_dataset_envelope(
    source: Path,
    *,
    catalog_root: Path,
    name: str,
    provenance: str | None = None,
) -> RegisteredEnvelope:
    """Copy a host-resolved dataset into a content-addressed trusted catalog."""
    source_path = source.expanduser().resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"Trusted Harbor dataset not found: {source_path}")
    # Validate the source before any partial catalog entry is created.
    _tree_entries(source_path)
    source_dataset = HarborDataset.from_ref(DatasetRef(uri=source_path.as_uri(), metadata={"id": name}))

    task_sources: list[tuple[str, Path, str, TaskEnvelopePolicy]] = []
    for task in source_dataset.tasks:
        task_path = local_path_from_uri(task.uri, context="Trusted Harbor task").resolve()
        relative = task_path.relative_to(source_path).as_posix()
        if relative == "":
            relative = "."
        task_sources.append((task.id, task_path, relative, _policy_for_task(task_path)))

    source_digest = tree_digest(source_path, exclude={ENVELOPE_DESCRIPTOR_FILENAME})
    envelope_id = f"{_slug(name)}-{source_digest.removeprefix('sha256:')[:16]}"
    envelope_root = catalog_root.expanduser().resolve() / "envelopes" / envelope_id
    dataset_path = envelope_root / "dataset"
    manifest_path = envelope_root / ENVELOPE_MANIFEST_FILENAME

    if envelope_root.exists():
        manifest = TrustedEnvelopeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.envelope_digest != source_digest:
            raise ValueError(f"Trusted envelope id collision: {envelope_id}")
        return RegisteredEnvelope(manifest=manifest, dataset_path=dataset_path)

    envelope_root.parent.mkdir(parents=True, exist_ok=True)
    partial = envelope_root.with_name(f".{envelope_root.name}.{os.getpid()}.partial")
    if partial.exists():
        shutil.rmtree(partial)
    try:
        _safe_copy_tree(source_path, partial / "dataset")
        tasks = [
            TrustedTaskManifest(
                task_id=task_id,
                path=relative,
                content_digest=tree_digest(
                    partial / "dataset" if relative == "." else partial / "dataset" / relative,
                    exclude={ENVELOPE_DESCRIPTOR_FILENAME},
                ),
                policy=policy,
            )
            for task_id, _task_path, relative, policy in task_sources
        ]
        manifest = TrustedEnvelopeManifest(
            envelope_id=envelope_id,
            envelope_digest=source_digest,
            source=provenance or str(source_path),
            tasks=tasks,
        )
        descriptor = TrustedEnvelopeDescriptor(
            envelope_id=manifest.envelope_id,
            envelope_digest=manifest.envelope_digest,
            tasks=manifest.tasks,
        )
        (partial / ENVELOPE_MANIFEST_FILENAME).write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        (partial / "dataset" / ENVELOPE_DESCRIPTOR_FILENAME).write_text(
            descriptor.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(partial, envelope_root)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return RegisteredEnvelope(manifest=manifest, dataset_path=dataset_path)


def _descriptor_at(dataset_path: Path, task_path: Path) -> tuple[TrustedEnvelopeDescriptor, Path]:
    candidates = (
        task_path / ENVELOPE_DESCRIPTOR_FILENAME,
        dataset_path / ENVELOPE_DESCRIPTOR_FILENAME,
    )
    for path in candidates:
        if path.is_file():
            try:
                return TrustedEnvelopeDescriptor.model_validate_json(path.read_text(encoding="utf-8")), path.parent
            except (OSError, UnicodeError, ValueError) as exc:
                raise ValueError(f"Invalid trusted envelope descriptor {path}: {exc}") from exc
    raise ValueError(
        f"Harbor task is not bound to a trusted host envelope: {task_path}. "
        "Run it through the Experimentalist host launcher."
    )


def resolve_envelope_task(dataset_path: Path, task_path: Path, *, task_id: str) -> ResolvedEnvelopeTask:
    """Resolve one local task against its host-generated envelope descriptor."""
    descriptor, descriptor_root = _descriptor_at(dataset_path.resolve(), task_path.resolve())
    relative = task_path.resolve().relative_to(descriptor_root.resolve()).as_posix()
    if relative == "":
        relative = "."

    matches = [task for task in descriptor.tasks if task.path == relative]
    if not matches and len(descriptor.tasks) == 1 and descriptor.tasks[0].path == ".":
        # Eval Author copies a one-task template into per-trace directories. The
        # copied descriptor still intentionally binds each derivative to that base.
        matches = descriptor.tasks
    if len(matches) != 1:
        raise ValueError(f"Trusted envelope descriptor does not bind task path {task_path}")
    base = matches[0]
    return ResolvedEnvelopeTask(
        envelope_id=descriptor.envelope_id,
        envelope_digest=descriptor.envelope_digest,
        task_id=task_id,
        base_task_id=base.task_id,
        task_path=task_path.resolve(),
        policy=base.policy,
    )


def create_overlay_directory(bindings: list[ResolvedEnvelopeTask], destination: Path) -> str | None:
    """Copy only declared mutable files into a request-scoped overlay tree."""
    copied = False
    destination.mkdir(parents=True, exist_ok=False)
    for binding in bindings:
        allowed = [*binding.policy.task_data_paths, *binding.policy.verifier_paths]
        for declared in allowed:
            source = binding.task_path / declared
            if not source.exists():
                continue
            target = destination / binding.task_id / declared
            if source.is_symlink():
                raise ValueError(f"Task overlay contains a symbolic link: {source}")
            if source.is_dir():
                _safe_copy_tree(source, target)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            else:
                raise ValueError(f"Task overlay contains a special file: {source}")
            copied = True
    if not copied:
        shutil.rmtree(destination)
        return None
    return transport_tree_digest(destination)


def _task_path(dataset_root: Path, task: TrustedTaskManifest) -> Path:
    return dataset_root if task.path == "." else dataset_root / task.path


def _set_materialized_identity(task_dir: Path, task_id: str, base_task_id: str) -> None:
    if task_id == base_task_id:
        return
    toml_path = task_dir / "task.toml"
    document = tomlkit.parse(toml_path.read_text(encoding="utf-8"))
    task_table = document.get("task")
    if task_table is None:
        raise ValueError(f"Trusted Harbor task has no [task] table: {toml_path}")
    raw_name = task_table.get("name")
    if not isinstance(raw_name, str) or "/" not in raw_name:
        raise ValueError(f"Trusted Harbor task name must use org/name format: {raw_name!r}")
    organization, short_name = raw_name.rsplit("/", 1)
    base_name = short_name.split("__", 1)[0]
    task_table["name"] = f"{organization}/{base_name}__{task_id}"
    metadata = document.get("metadata")
    if metadata is None:
        metadata = tomlkit.table()
        document["metadata"] = metadata
    provenance = metadata.get("nemo_experimentalist")
    if provenance is None:
        provenance = tomlkit.table()
        metadata["nemo_experimentalist"] = provenance
    provenance["trusted_envelope_base_task"] = base_task_id
    toml_path.write_text(tomlkit.dumps(document), encoding="utf-8")


def _validate_task_data_file(path: Path, slot: TaskDataSlot) -> None:
    size = path.stat().st_size
    if size > slot.max_bytes:
        raise ValueError(f"Task-data overlay exceeds {slot.max_bytes} bytes: {slot.path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ValueError(f"Task-data overlay must be UTF-8 {slot.media_type}: {slot.path}") from exc
    if slot.media_type == "application/json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Task-data overlay is not valid JSON: {slot.path}: {exc}") from exc


class TrustedEnvelopeCatalog:
    """Read-only catalog and materializer used exclusively by the host bridge."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Trusted Harbor envelope catalog not found: {self.root}")

    def load(self, envelope_id: str, envelope_digest: str) -> tuple[TrustedEnvelopeManifest, Path]:
        envelope_root = self.root / "envelopes" / envelope_id
        try:
            envelope_root.resolve().relative_to((self.root / "envelopes").resolve())
        except ValueError as exc:
            raise ValueError(f"Trusted envelope id escapes the catalog: {envelope_id!r}") from exc
        manifest_path = envelope_root / ENVELOPE_MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise KeyError(envelope_id)
        manifest = TrustedEnvelopeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.envelope_id != envelope_id or manifest.envelope_digest != envelope_digest:
            raise ValueError(f"Trusted envelope identity mismatch: {envelope_id}")
        dataset_root = envelope_root / "dataset"
        current_digest = tree_digest(dataset_root, exclude={ENVELOPE_DESCRIPTOR_FILENAME})
        if current_digest != manifest.envelope_digest:
            raise ValueError(f"Trusted envelope content changed after registration: {envelope_id}")
        return manifest, dataset_root

    def materialize(
        self,
        *,
        envelope_id: str,
        envelope_digest: str,
        selections: list[EnvelopeTaskSelection],
        destination: Path,
        overlay_dir: Path | None = None,
    ) -> Path:
        """Materialize selected immutable tasks and apply only declared overlays."""
        manifest, dataset_root = self.load(envelope_id, envelope_digest)
        tasks = {task.task_id: task for task in manifest.tasks}
        destination.mkdir(parents=True, exist_ok=False)
        selected_ids = {selection.task_id for selection in selections}
        if len(selected_ids) != len(selections):
            raise ValueError("Materialized task ids must be unique")

        if overlay_dir is not None:
            overlay_task_dirs = {path.name for path in overlay_dir.iterdir()}
            unexpected = overlay_task_dirs - selected_ids
            if unexpected:
                raise ValueError(f"Task overlay contains unknown task ids: {', '.join(sorted(unexpected))}")

        for selection in selections:
            try:
                base = tasks[selection.base_task_id]
            except KeyError as exc:
                raise ValueError(f"Trusted envelope {envelope_id} has no task {selection.base_task_id!r}") from exc
            source = _task_path(dataset_root, base)
            if tree_digest(source, exclude={ENVELOPE_DESCRIPTOR_FILENAME}) != base.content_digest:
                raise ValueError(f"Trusted task content changed after registration: {selection.base_task_id}")
            target = destination / selection.task_id
            _safe_copy_tree(source, target)
            (target / ENVELOPE_DESCRIPTOR_FILENAME).unlink(missing_ok=True)

            task_overlay = overlay_dir / selection.task_id if overlay_dir is not None else None
            if task_overlay is not None and task_overlay.exists():
                for path in sorted(task_overlay.rglob("*")):
                    relative = path.relative_to(task_overlay).as_posix()
                    if path.name in _FORBIDDEN_OVERLAY_FILENAMES:
                        raise ValueError(
                            f"Task overlay may not modify runtime-control file {selection.task_id}/{relative}"
                        )
                    if path.is_dir():
                        continue
                    task_data_slot = next(
                        (slot for slot in base.policy.task_data if slot.path == relative),
                        None,
                    )
                    verifier_allowed = path_is_allowed(relative, base.policy.verifier_paths)
                    if task_data_slot is None and not verifier_allowed:
                        raise ValueError(f"Task overlay may not modify undeclared path {selection.task_id}/{relative}")
                    if path.is_symlink() or not path.is_file():
                        raise ValueError(f"Task overlay contains an unsupported file: {path}")
                    if task_data_slot is not None:
                        _validate_task_data_file(path, task_data_slot)
                    output = target / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, output)
            _set_materialized_identity(target, selection.task_id, selection.base_task_id)
        return destination


def task_config(task_dir: Path) -> dict[str, object]:
    """Return the raw task TOML for focused policy and test assertions."""
    return tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
