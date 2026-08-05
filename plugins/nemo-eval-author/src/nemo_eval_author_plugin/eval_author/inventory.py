# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable, content-addressed context for existing Harbor task sets."""

import base64
import copy
import hashlib
import json
import math
import tomllib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal, Self, cast

from harbor.models.task.task import Task as HarborTask
from nemo_eval_author_plugin.eval_author.models import AuthoredMetric, AuthoredMetricContract
from nemo_experimentalist_plugin.entities import DatasetRef, local_path_from_uri
from pydantic import BaseModel, ConfigDict

_PROVENANCE_METADATA_NAMESPACE = "nemo_experimentalist"
_SOURCE_TRACE_PROVENANCE_KEYS = ("source_trace_ref", "source_trace_refs")
_METRIC_CONTRACT_METADATA_KEY = "metric_contract"


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_json_value(value: object) -> object:
    if isinstance(value, datetime):
        kind = "toml-offset-datetime" if value.utcoffset() is not None else "toml-local-datetime"
        return [kind, value.isoformat()]
    if isinstance(value, date):
        return ["toml-date", value.isoformat()]
    if isinstance(value, time):
        return ["toml-time", value.isoformat()]
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("inventory identity cannot include non-finite numbers")
        return ["float", value.hex()]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("inventory identity object keys must be strings")
        return [
            "table",
            [[key, _canonical_json_value(value[key])] for key in sorted(value)],
        ]
    if isinstance(value, list):
        return ["array", [_canonical_json_value(item) for item in value]]
    if isinstance(value, tuple):
        return ["tuple", [_canonical_json_value(item) for item in value]]
    raise TypeError(f"inventory identity cannot encode {type(value).__name__}")


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


class InventoryVerifierFile(BaseModel):
    """One verifier file represented without a host filesystem path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    content_hash: str
    content: str
    content_encoding: Literal["utf-8", "base64"]


class InventoryVerifierLayout(BaseModel):
    """Representative task-relative layout for one verifier family."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    directory: str
    entrypoint: str | None
    files: tuple[InventoryVerifierFile, ...]


class VerifierFamilyInventory(BaseModel):
    """Unique verifier implementation and the tasks that use it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: str
    representative_task_id: str
    task_ids: tuple[str, ...]
    layout: InventoryVerifierLayout
    metric_keys: tuple[str, ...]


class ReferenceTaskInventory(BaseModel):
    """Read-only facts about one existing reference task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    source_task_set_identity: str
    source_trace_refs: tuple[str, ...]
    fingerprint: str
    verifier_family_hash: str
    metric_keys: tuple[str, ...]


class ExistingMetricContract(AuthoredMetric):
    """Known existing metric name and the verifier families that emit it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verifier_family_hashes: tuple[str, ...]


class DuplicateInventoryGroup(BaseModel):
    """Tasks sharing one normalized fingerprint or provenance value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    task_ids: tuple[str, ...]


class ReferenceTaskSetInventory(BaseModel):
    """Content-addressed immutable view of all existing reference task sets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: str
    task_set_identities: tuple[str, ...]
    tasks: tuple[ReferenceTaskInventory, ...]
    verifier_families: tuple[VerifierFamilyInventory, ...]
    metric_keys: tuple[str, ...]
    metric_contracts: tuple[ExistingMetricContract, ...]
    duplicate_fingerprints: tuple[DuplicateInventoryGroup, ...]
    duplicate_provenance: tuple[DuplicateInventoryGroup, ...]

    @classmethod
    def empty(cls) -> Self:
        """Return the canonical inventory for no existing reference task sets."""
        return cls.model_validate(build_reference_task_set_inventory(()).model_dump())


@dataclass(frozen=True, slots=True)
class _TaskSnapshot:
    task_id: str
    source_task_set_identity: str
    source_trace_refs: tuple[str, ...]
    fingerprint: str
    verifier_family_hash: str
    verifier_layout: InventoryVerifierLayout
    metric_contracts: tuple[AuthoredMetric, ...]

    @property
    def metric_keys(self) -> tuple[str, ...]:
        return tuple(metric.key for metric in self.metric_contracts)


def build_reference_task_set_inventory(
    reference_task_sets: Sequence[DatasetRef],
) -> ReferenceTaskSetInventory:
    """Build immutable existing-suite context directly from local task-set refs.

    Dataset split metadata and absolute source paths are deliberately excluded
    from every identity and returned model.
    """
    snapshots: list[_TaskSnapshot] = []
    task_set_identities: list[str] = []
    for reference in reference_task_sets:
        source_root = local_path_from_uri(reference.uri, context="Eval Author reference task set").expanduser()
        if source_root.is_symlink():
            raise ValueError(f"Eval Author reference task set root must not be a symbolic link: {source_root}")
        root = source_root.resolve()
        _reject_symbolic_links(root)
        task_dirs = _selected_task_dirs(root, reference)
        reference_metric_contracts = _metric_contracts_from_metadata(cast(Mapping[str, object], reference.metadata))
        task_snapshots = sorted(
            (
                replace(
                    snapshot,
                    metric_contracts=_merge_metric_contracts(
                        reference_metric_contracts,
                        snapshot.metric_contracts,
                    ),
                )
                for snapshot in (_snapshot_task(task_dir) for task_dir in task_dirs)
            ),
            key=lambda task: (task.task_id, task.fingerprint, task.source_trace_refs),
        )
        task_set_identity = _canonical_digest(
            [
                {
                    "task_id": task.task_id,
                    "source_trace_refs": task.source_trace_refs,
                    "fingerprint": task.fingerprint,
                    "verifier_family_hash": task.verifier_family_hash,
                    "metric_contracts": tuple(contract.model_dump(mode="json") for contract in task.metric_contracts),
                }
                for task in task_snapshots
            ]
        )
        task_set_identities.append(task_set_identity)
        snapshots.extend(replace(task, source_task_set_identity=task_set_identity) for task in task_snapshots)

    ordered_snapshots = tuple(
        sorted(
            snapshots,
            key=lambda task: (
                task.task_id,
                task.source_task_set_identity,
                task.fingerprint,
                task.source_trace_refs,
            ),
        )
    )
    tasks = tuple(
        ReferenceTaskInventory(
            task_id=task.task_id,
            source_task_set_identity=task.source_task_set_identity,
            source_trace_refs=task.source_trace_refs,
            fingerprint=task.fingerprint,
            verifier_family_hash=task.verifier_family_hash,
            metric_keys=task.metric_keys,
        )
        for task in ordered_snapshots
    )
    verifier_families = _verifier_families(ordered_snapshots)
    metric_contracts = _existing_metric_contracts(ordered_snapshots)
    metric_keys = tuple(contract.key for contract in metric_contracts)
    duplicate_fingerprints = _duplicate_groups((task.fingerprint, task.task_id) for task in tasks)
    duplicate_provenance = _duplicate_groups(
        (trace_ref, task.task_id) for task in tasks for trace_ref in task.source_trace_refs
    )
    inventory_payload = {
        "task_set_identities": tuple(sorted(task_set_identities)),
        "tasks": tuple(task.model_dump(mode="json") for task in tasks),
        "verifier_families": tuple(family.model_dump(mode="json") for family in verifier_families),
        "metric_keys": metric_keys,
        "metric_contracts": tuple(contract.model_dump(mode="json") for contract in metric_contracts),
        "duplicate_fingerprints": tuple(group.model_dump(mode="json") for group in duplicate_fingerprints),
        "duplicate_provenance": tuple(group.model_dump(mode="json") for group in duplicate_provenance),
    }
    return ReferenceTaskSetInventory(
        identity=_canonical_digest(inventory_payload),
        task_set_identities=tuple(sorted(task_set_identities)),
        tasks=tasks,
        verifier_families=verifier_families,
        metric_keys=metric_keys,
        metric_contracts=metric_contracts,
        duplicate_fingerprints=duplicate_fingerprints,
        duplicate_provenance=duplicate_provenance,
    )


def _reject_symbolic_links(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Eval Author reference task sets must not contain symbolic links: {path}")


def _selected_task_dirs(root: Path, reference: DatasetRef) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Eval Author reference task set not found: {root}")
    if not root.is_dir():
        raise ValueError(f"Eval Author reference task set must be a directory: {root}")
    if (root / "task.toml").is_file():
        task_dirs = [root]
    else:
        task_dirs = sorted(
            path
            for path in root.iterdir()
            if path.is_dir() and path.name != "task_template" and (path / "task.toml").is_file()
        )
    if not task_dirs:
        raise ValueError(f"Eval Author reference task set contains no Harbor tasks: {root}")

    selected = reference.metadata.get("task_ids")
    if selected is None:
        return task_dirs
    if (
        not isinstance(selected, list | tuple)
        or not selected
        or any(not isinstance(task_id, str) or not task_id for task_id in selected)
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("reference task-set metadata field 'task_ids' must be a non-empty unique list of strings")
    by_id = {path.name: path for path in task_dirs}
    missing = set(selected) - set(by_id)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"reference task ids not found: {missing_text}")
    return [by_id[task_id] for task_id in selected]


def _snapshot_task(task_dir: Path) -> _TaskSnapshot:
    config_path = task_dir / "task.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    harbor_task = HarborTask(task_dir)
    verifier_dir = _verifier_dir(task_dir, config, harbor_task)
    verifier_layout = _verifier_layout(task_dir, verifier_dir)
    verifier_family_hash = _canonical_digest(
        {
            "directory": verifier_layout.directory,
            "entrypoint": verifier_layout.entrypoint,
            "files": [{"path": file.path, "content_hash": file.content_hash} for file in verifier_layout.files],
        }
    )
    return _TaskSnapshot(
        task_id=task_dir.name,
        source_task_set_identity="",
        source_trace_refs=_source_trace_refs(config),
        fingerprint=_task_fingerprint(task_dir, verifier_dir, config),
        verifier_family_hash=verifier_family_hash,
        verifier_layout=verifier_layout,
        metric_contracts=_declared_metric_contracts(config),
    )


def _verifier_dir(task_dir: Path, config: dict[str, object], harbor_task: HarborTask) -> Path:
    verifier = config.get("verifier")
    if isinstance(verifier, dict):
        configured = verifier.get("directory")
        if isinstance(configured, str) and configured.strip():
            configured_path = Path(configured)
            candidate = configured_path if configured_path.is_absolute() else task_dir / configured_path
        else:
            candidate = harbor_task.paths.tests_dir
    else:
        candidate = harbor_task.paths.tests_dir
    candidate = candidate.resolve()
    try:
        candidate.relative_to(task_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"reference task verifier must be contained in its task: {candidate}") from exc
    return candidate


def _verifier_layout(task_dir: Path, verifier_dir: Path) -> InventoryVerifierLayout:
    directory = verifier_dir.relative_to(task_dir.resolve()).as_posix()
    files = tuple(_inventory_file(path, verifier_dir) for path in _files_under(verifier_dir))
    entrypoint = next(
        (
            candidate
            for candidate in ("test.sh", "test.ps1", "test.cmd", "test.bat")
            if any(file.path == candidate for file in files)
        ),
        None,
    )
    return InventoryVerifierLayout(directory=directory, entrypoint=entrypoint, files=files)


def _files_under(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"reference verifier inventory does not follow symbolic links: {path}")
        if path.is_file():
            files.append(path)
    return files


def _inventory_file(path: Path, root: Path) -> InventoryVerifierFile:
    content_bytes = path.read_bytes()
    try:
        content = content_bytes.decode("utf-8")
        encoding: Literal["utf-8", "base64"] = "utf-8"
    except UnicodeDecodeError:
        content = base64.b64encode(content_bytes).decode("ascii")
        encoding = "base64"
    return InventoryVerifierFile(
        path=path.relative_to(root).as_posix(),
        content_hash=_sha256_bytes(content_bytes),
        content=content,
        content_encoding=encoding,
    )


def _source_trace_refs(config: dict[str, object]) -> tuple[str, ...]:
    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    provenance = metadata.get(_PROVENANCE_METADATA_NAMESPACE)
    if not isinstance(provenance, dict):
        return ()
    values: set[str] = set()
    for key in _SOURCE_TRACE_PROVENANCE_KEYS:
        item = provenance.get(key)
        if isinstance(item, str) and item:
            values.add(item)
        elif isinstance(item, list):
            values.update(entry for entry in item if isinstance(entry, str) and entry)
    return tuple(sorted(values))


def _task_fingerprint(task_dir: Path, verifier_dir: Path, config: dict[str, object]) -> str:
    normalized_config = copy.deepcopy(config)
    normalized_config.pop("verifier", None)
    task_table = normalized_config.get("task")
    if isinstance(task_table, dict):
        task_table.pop("name", None)
    metadata = normalized_config.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop(_PROVENANCE_METADATA_NAMESPACE, None)
        metadata.pop(_METRIC_CONTRACT_METADATA_KEY, None)
        owned = metadata.get("nemo_eval_author")
        if isinstance(owned, dict):
            owned.pop(_METRIC_CONTRACT_METADATA_KEY, None)
            if not owned:
                metadata.pop("nemo_eval_author", None)
        if not metadata:
            normalized_config.pop("metadata", None)

    verifier_relative = verifier_dir.relative_to(task_dir.resolve())
    files: list[dict[str, str]] = []
    for path in sorted(task_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Eval Author reference tasks must not contain symbolic links: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(task_dir)
        if relative == Path("task.toml") or relative == verifier_relative or verifier_relative in relative.parents:
            continue
        content = path.read_bytes()
        try:
            normalized_content = content.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            normalized_content = content
        files.append(
            {
                "path": relative.as_posix(),
                "content_hash": _sha256_bytes(normalized_content),
            }
        )
    return _canonical_digest({"config": normalized_config, "files": files})


def _declared_metric_contracts(config: dict[str, object]) -> tuple[AuthoredMetric, ...]:
    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    return _metric_contracts_from_metadata(cast(Mapping[str, object], metadata))


def _metric_contracts_from_metadata(metadata: Mapping[str, object]) -> tuple[AuthoredMetric, ...]:
    candidates: list[object] = []
    direct = metadata.get("metric_contract")
    if direct is not None:
        candidates.append(direct)
    owned = metadata.get("nemo_eval_author")
    if isinstance(owned, Mapping) and owned.get("metric_contract") is not None:
        candidates.append(cast(Mapping[str, object], owned)["metric_contract"])
    if not candidates:
        return ()
    if len(candidates) > 1:
        raise ValueError("reference task declares multiple metric_contract metadata values")
    return AuthoredMetricContract.model_validate(candidates[0]).metrics


def _merge_metric_contracts(
    *groups: tuple[AuthoredMetric, ...],
) -> tuple[AuthoredMetric, ...]:
    declarations: dict[str, AuthoredMetric] = {}
    for metric in (metric for group in groups for metric in group):
        existing = declarations.get(metric.key)
        if existing is not None and existing != metric:
            raise ValueError(f"conflicting explicit metric contract for key {metric.key!r}")
        declarations[metric.key] = metric
    return tuple(declarations[key] for key in sorted(declarations))


def _existing_metric_contracts(snapshots: tuple[_TaskSnapshot, ...]) -> tuple[ExistingMetricContract, ...]:
    declarations: dict[str, AuthoredMetric] = {}
    families: dict[str, set[str]] = defaultdict(set)
    for snapshot in snapshots:
        for metric in snapshot.metric_contracts:
            existing = declarations.get(metric.key)
            if existing is not None and existing != metric:
                raise ValueError(f"conflicting explicit metric contract for key {metric.key!r}")
            declarations[metric.key] = metric
            families[metric.key].add(snapshot.verifier_family_hash)
    return tuple(
        ExistingMetricContract(
            **declarations[key].model_dump(),
            verifier_family_hashes=tuple(sorted(families[key])),
        )
        for key in sorted(declarations)
    )


def _verifier_families(snapshots: tuple[_TaskSnapshot, ...]) -> tuple[VerifierFamilyInventory, ...]:
    grouped: dict[str, list[_TaskSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.verifier_family_hash].append(snapshot)
    return tuple(
        VerifierFamilyInventory(
            identity=identity,
            representative_task_id=min(task.task_id for task in family),
            task_ids=tuple(sorted(task.task_id for task in family)),
            layout=family[0].verifier_layout,
            metric_keys=tuple(sorted({key for task in family for key in task.metric_keys})),
        )
        for identity, family in sorted(grouped.items())
    )


def _duplicate_groups(values: Iterable[tuple[str, str]]) -> tuple[DuplicateInventoryGroup, ...]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for value, task_id in values:
        grouped[value].append(task_id)
    return tuple(
        DuplicateInventoryGroup(value=value, task_ids=tuple(sorted(task_ids)))
        for value, task_ids in sorted(grouped.items())
        if len(task_ids) > 1
    )
