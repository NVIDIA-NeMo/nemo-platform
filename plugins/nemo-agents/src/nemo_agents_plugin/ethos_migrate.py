# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Move an agent's Ethos artifacts from their pre-rename names to their final ones.

This module and its tests are the only places in the plugin allowed to name the
pre-rename artifact, because migration owns every old-name lookup. Nothing here
is a runtime alias: the old key and the old filename are read solely so they can
be rewritten, and no other code path accepts them.

The command performs one hard rename:

* local package ``<agents-root>/<agent>-spec/`` to ``<agents-root>/<agent>-ethos/``
* contract file ``AGENT-SPEC.md`` to ``ETHOS.md``
* Fileset ``<agent>-spec`` to ``<agent>-ethos``
* affected ``optimizer.yaml`` keys and paths to ``ethos``

The apply path is a compensating transaction. Its binding rule: **every
controlled failure before the final verification leaves the old local package,
the old Fileset, and the old profile keys authoritative.**

:class:`_TransactionRecord` is the single source of truth for the transaction. It
is held in memory, persisted to a journal outside the repository, and is the only
input recovery reads, so a later run with different arguments can never redirect
recovery at a path the failed run never touched.

Platform access goes through the two narrow ports :class:`FilesetStore` and
:class:`JobStore`, so the transaction is testable against real files without a
running platform. :class:`SdkFilesetStore` and :class:`SdkJobStore` bind them to
the platform SDK.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

import yaml
from nemo_agents_plugin.entities import ETHOS_FILENAME, ETHOS_LOCAL_ROOT, ethos_fileset_name
from nemo_agents_plugin.ethos_parse import EthosParseError, parse_ethos
from nemo_platform_plugin.config import nmp_user_data_dir
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-rename vocabulary — read here only so it can be rewritten
# ---------------------------------------------------------------------------

LEGACY_CONTRACT_FILENAME = "AGENT-SPEC.md"
LEGACY_PACKAGE_SUFFIX = "-spec"
LEGACY_PROFILE_KEY = "agent_spec"
LEGACY_WRITER_SKILL = "nemo-spec"

ETHOS_PROFILE_KEY = "ethos"
ETHOS_WRITER_SKILL = "nemo-ethos"
PROFILE_FILENAME = "optimizer.yaml"
JOURNAL_ROOT_NAME = "ethos-migrations"
JOURNAL_FILENAME = "journal.json"

INSIGHTS_JOB_SOURCE = "insights"
EXPERIMENT_STATE_DIRNAME = "eval-and-optimize"
EXPERIMENT_DEFAULT_ROOT = (".nemo-optimizer", "experiments")
COMPLETED_RUN_STATUS = "completed"

# Names that legitimately keep the old substring. They are masked out of a line
# before the banned terms are searched, which is how a longer allowed term wins
# over a shorter banned one.
_ALLOWED_LEGACY_TERMS: tuple[str, ...] = (
    "nemo-agents-spec-v1",
    "agent-specific",
    "agent-specified",
)

# Longest first, so ``AGENT-SPEC.md`` is never reported as ``agent-spec``.
_BANNED_LEGACY_TERMS: tuple[str, ...] = tuple(
    sorted(
        (
            LEGACY_CONTRACT_FILENAME,
            LEGACY_WRITER_SKILL,
            LEGACY_PROFILE_KEY,
            "AGENT_SPEC",
            "AgentSpec",
            "agent-spec",
            "parse_spec",
            "SpecParseError",
            "agent spec",
        ),
        key=len,
        reverse=True,
    )
)

# Must agree with ``ethos_parse``: the front matter fence is anchored at offset
# zero and a section heading is ``## `` at the start of a line. The staged file
# goes through ``parse_ethos`` afterwards, so any drift fails loudly there.
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
_LEGACY_TITLE_RE = re.compile(r"^#\s+Agent Spec:", re.MULTILINE)


# ---------------------------------------------------------------------------
# Errors and outcomes
# ---------------------------------------------------------------------------


class MigrationError(RuntimeError):
    """A controlled migration failure. The old state stays authoritative."""


class RecoveryRequired(MigrationError):
    """Compensation failed. The journal and backups are kept for the next run."""


class Outcome(str, Enum):
    """State-table outcome for one invocation."""

    NOTHING_TO_MIGRATE = "nothing-to-migrate"
    ALREADY_MIGRATED = "already-migrated"
    PENDING = "pending"
    MIGRATED = "migrated"
    RECOVERED = "recovered"
    RECOVERY_REQUIRED = "recovery-required"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class _TargetState(str, Enum):
    """Durable ownership state for one final target."""

    ABSENT = "absent"
    PRE_EXISTING = "pre-existing"
    CREATING = "creating"
    OWNED = "owned"


_OK_OUTCOMES = frozenset(
    {
        Outcome.NOTHING_TO_MIGRATE,
        Outcome.ALREADY_MIGRATED,
        Outcome.PENDING,
        Outcome.MIGRATED,
        Outcome.RECOVERED,
    }
)


@dataclass
class MigrationReport:
    """What the command did, plus the human-readable lines it printed."""

    outcome: Outcome
    lines: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """False for a conflict, a blocked run, or pending recovery; the CLI exits 1."""
        return self.outcome in _OK_OUTCOMES


@dataclass(frozen=True)
class MigrationRequest:
    """One agent in one workspace, plus the paths the caller could name."""

    agent: str
    workspace: str = "default"
    agents_root: Path = Path(ETHOS_LOCAL_ROOT)
    profiles: tuple[Path, ...] = ()
    experiment_dirs: tuple[Path, ...] = ()
    dry_run: bool = False
    start_dir: Path | None = None


# ---------------------------------------------------------------------------
# Filesystem seams
#
# Every mutating filesystem call the transaction makes goes through one of these
# three functions, so a test can fail a specific copy, removal, or profile write
# at its real boundary instead of through a hook in the transaction itself.
# ---------------------------------------------------------------------------


def _copy_tree(source: Path, destination: Path) -> None:
    """Copy a directory tree, refusing to write over an existing destination.

    ``dirs_exist_ok`` stays false so a destination that appeared after assessment
    raises :class:`FileExistsError` instead of being merged into or replaced.
    """
    shutil.copytree(source, destination)


def _copy_file(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path)


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileFingerprint:
    """Size and digest of one regular file."""

    size: int
    sha256: str


Manifest = dict[str, FileFingerprint]


def build_manifest(root: Path) -> Manifest:
    """Fingerprint every regular file under *root*, keyed by relative POSIX path.

    A symlinked root, a symlink anywhere beneath it, and a path that escapes the
    root are all rejected rather than skipped: the Fileset upload follows a
    symlink and ships its target's bytes, so tolerating one would move content
    from outside the package and hide it from every comparison made here.
    """
    if root.is_symlink():
        raise MigrationError(
            f"{root} is a symlink; migration copies, uploads, and deletes this path, so following "
            "it could reach content outside the agents root. Replace it with a real directory"
        )
    resolved_root = root.resolve()
    manifest: Manifest = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for name in sorted(dirnames + filenames):
            path = here / name
            if path.is_symlink():
                rel = path.relative_to(root).as_posix()
                raise MigrationError(
                    f"{root} contains symlink {rel!r}; migration copies and uploads bytes, so a "
                    "symlink would move content from outside the package. Replace it with a "
                    "regular file, or move its target inside the package"
                )
        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(root).as_posix()
            if not path.is_file():
                raise MigrationError(f"{root} contains {rel!r}, which is not a regular file")
            if not path.resolve().is_relative_to(resolved_root):
                raise MigrationError(f"{root} contains {rel!r}, which resolves outside the package")
            manifest[rel] = _fingerprint(path)
    return dict(sorted(manifest.items()))


def _fingerprint(path: Path) -> FileFingerprint:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return FileFingerprint(size=size, sha256=digest.hexdigest())


def _manifest_to_json(manifest: Manifest | None) -> dict[str, dict[str, Any]] | None:
    if manifest is None:
        return None
    return {rel: {"size": fp.size, "sha256": fp.sha256} for rel, fp in manifest.items()}


def _manifest_from_json(payload: object, label: str) -> Manifest | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object or null")

    manifest: Manifest = {}
    for rel, entry in payload.items():
        if not isinstance(rel, str) or not _is_safe_relative_path(rel):
            raise ValueError(f"{label} contains invalid relative path {rel!r}")
        if not isinstance(entry, dict):
            raise ValueError(f"{label}[{rel!r}] must be an object")
        size = entry.get("size")
        digest = entry.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"{label}[{rel!r}].size must be a non-negative integer")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label}[{rel!r}].sha256 must be a lowercase SHA-256 digest")
        manifest[rel] = FileFingerprint(size=size, sha256=digest)
    return manifest


def _is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return value not in {"", "."} and not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


# ---------------------------------------------------------------------------
# Platform ports
# ---------------------------------------------------------------------------


class FilesetStore(Protocol):
    """The Fileset operations migration needs.

    ``create`` must be conditional: it returns ``True`` only when this call
    created the Fileset, and ``False`` when it already existed. That is what
    makes target ownership decidable without a read-then-write race, so the
    transaction never deletes a Fileset another writer created. ``upload`` must
    not auto-create, so a Fileset can only come into existence through
    ``create``.

    The list API carries no checksum, so remote bytes are verified by
    downloading them and computing the same local manifest.
    """

    def exists(self, *, workspace: str, name: str) -> bool: ...

    def create(self, *, workspace: str, name: str) -> bool: ...

    def download(self, *, workspace: str, name: str, dest: Path) -> None: ...

    def upload(self, *, workspace: str, name: str, source: Path) -> None: ...

    def delete(self, *, workspace: str, name: str) -> None: ...


@dataclass(frozen=True)
class JobRecord:
    """The generic Platform Jobs fields the Insights gate reads."""

    name: str
    workspace: str
    source: str
    status: str
    spec: dict[str, Any]


class JobStore(Protocol):
    """Workspace-scoped listing over the generic Platform Jobs API."""

    def list_jobs(self, *, workspace: str) -> list[JobRecord]: ...


@dataclass(frozen=True)
class SdkFilesetStore:
    """Bind :class:`FilesetStore` to the platform SDK's Files resource."""

    sdk: Any

    def exists(self, *, workspace: str, name: str) -> bool:
        from nemo_platform import NotFoundError as PlatformNotFoundError
        from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError

        try:
            self.sdk.files.filesets.retrieve(name, workspace=workspace)
        except (PlatformNotFoundError, PluginClientNotFoundError):
            return False
        return True

    def create(self, *, workspace: str, name: str) -> bool:
        """Create the Fileset, returning False when it already existed.

        ``exist_ok`` stays at its default of false so the platform's 409 is the
        answer to "did this call create it?", rather than a check the caller
        makes separately and races against.
        """
        from nemo_platform import ConflictError

        try:
            self.sdk.files.filesets.create(name=name, workspace=workspace)
        except ConflictError:
            return False
        return True

    def download(self, *, workspace: str, name: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self.sdk.files.download(local_path=str(dest), fileset=name, workspace=workspace)

    def upload(self, *, workspace: str, name: str, source: Path) -> None:
        # Trailing slash uploads the directory's contents, not the directory.
        self.sdk.files.upload(
            local_path=f"{source}/",
            fileset=name,
            workspace=workspace,
            fileset_auto_create=False,
        )

    def delete(self, *, workspace: str, name: str) -> None:
        self.sdk.files.filesets.delete(name, workspace=workspace)


@dataclass(frozen=True)
class SdkJobStore:
    """Bind :class:`JobStore` to the generic Platform Jobs listing."""

    sdk: Any

    def list_jobs(self, *, workspace: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for job in self.sdk.jobs.list(workspace=workspace):
            status = getattr(job, "status", "")
            records.append(
                JobRecord(
                    name=str(getattr(job, "name", "") or ""),
                    workspace=str(getattr(job, "workspace", workspace) or workspace),
                    source=str(getattr(job, "source", "") or ""),
                    status=str(getattr(status, "value", status) or ""),
                    spec=dict(getattr(job, "spec", None) or {}),
                )
            )
        return records


# ---------------------------------------------------------------------------
# Name validation and plan
# ---------------------------------------------------------------------------


def validate_agent_name(agent: str) -> None:
    """Reject any agent name that is not one safe path component.

    The name is interpolated into a local package path that the transaction
    copies over and deletes, so a separator, ``..``, or an absolute value would
    let it reach outside ``--agents-root``.
    """
    if not agent:
        raise MigrationError("--name is required and cannot be empty")
    if "\0" in agent:
        raise MigrationError("--name cannot contain a NUL byte")
    if agent in {".", ".."}:
        raise MigrationError(f"--name {agent!r} is a directory reference, not an agent name")
    if "/" in agent or "\\" in agent or os.sep in agent or (os.altsep and os.altsep in agent):
        raise MigrationError(f"--name {agent!r} cannot contain a path separator")
    candidate = Path(agent)
    if candidate.is_absolute() or candidate.name != agent:
        raise MigrationError(
            f"--name {agent!r} must be a single path component, so the agent's package stays "
            "directly inside --agents-root"
        )


@dataclass(frozen=True)
class MigrationPlan:
    """Every location this invocation may read or write."""

    agent: str
    workspace: str
    agents_root: Path
    old_package: Path
    target_package: Path
    old_fileset: str
    target_fileset: str
    external_profiles: tuple[Path, ...]
    packaged_profiles: tuple[str, ...]
    experiment_dirs: tuple[Path, ...]


def _normalize_request(request: MigrationRequest) -> MigrationRequest:
    """Resolve every caller-supplied path against one captured working directory."""
    try:
        current = Path.cwd().resolve()
    except (OSError, RuntimeError) as exc:
        raise MigrationError(f"the current working directory cannot be resolved ({exc})") from exc

    def absolute(value: Path, label: str) -> Path:
        try:
            path = Path(value).expanduser()
            return (path if path.is_absolute() else current / path).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise MigrationError(f"{label} cannot be resolved to an absolute path ({exc})") from exc

    return MigrationRequest(
        agent=request.agent,
        workspace=request.workspace,
        agents_root=absolute(request.agents_root, "--agents-root"),
        profiles=tuple(absolute(path, "--profile") for path in request.profiles),
        experiment_dirs=tuple(absolute(path, "--experiment-dir") for path in request.experiment_dirs),
        dry_run=request.dry_run,
        start_dir=absolute(request.start_dir or current, "profile discovery start directory"),
    )


def journal_dir(workspace: str, agent: str) -> Path:
    """Transaction directory for one workspace-and-agent pair, outside the repository.

    The pair is hashed with a NUL separator so ``("a", "b-c")`` and ``("a-b", "c")``
    cannot collide, and ``--agents-root`` never moves the journal into a checkout
    where a crashed migration could land in a commit.
    """
    digest = hashlib.sha256(f"{workspace}\0{agent}".encode()).hexdigest()
    return (Path(nmp_user_data_dir()).expanduser() / JOURNAL_ROOT_NAME / digest).resolve()


def _build_plan(request: MigrationRequest) -> MigrationPlan:
    agents_root = request.agents_root
    old_package = agents_root / f"{request.agent}{LEGACY_PACKAGE_SUFFIX}"
    target_package = agents_root / ethos_fileset_name(request.agent)
    external, packaged = _discover_profiles(request, old_package, target_package)
    return MigrationPlan(
        agent=request.agent,
        workspace=request.workspace,
        agents_root=agents_root,
        old_package=old_package,
        target_package=target_package,
        old_fileset=f"{request.agent}{LEGACY_PACKAGE_SUFFIX}",
        target_fileset=ethos_fileset_name(request.agent),
        external_profiles=external,
        packaged_profiles=packaged,
        experiment_dirs=_discover_experiment_dirs(request, external, target_package),
    )


def _discover_profiles(
    request: MigrationRequest, old_package: Path, target_package: Path
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Split the affected profile set into external files and package-local copies.

    A profile inside either package travels with the package, so it is rewritten
    in the staged copy rather than edited in the legacy source. Containment
    decides that, not how the profile was discovered, so an explicit
    ``--profile`` pointing into the package is still treated as package-local.

    The command performs no global scan, so a profile outside this set is not
    discoverable and the caller must name it with ``--profile``.
    """
    candidates: list[Path] = [Path(profile) for profile in request.profiles]
    walked = _walk_up_for_profile(request.start_dir)
    if walked is not None:
        candidates.append(walked)
    for package in (old_package, target_package):
        if package.is_dir() and not package.is_symlink():
            candidates.extend(sorted(package.rglob(PROFILE_FILENAME)))

    external: dict[Path, None] = {}
    packaged: dict[str, None] = {}
    roots = [old_package.resolve(), target_package.resolve()]
    for candidate in _resolve_unique(candidates):
        for root in roots:
            if candidate.is_relative_to(root):
                packaged.setdefault(candidate.relative_to(root).as_posix(), None)
                break
        else:
            external.setdefault(candidate, None)
    return tuple(external), tuple(packaged)


def _walk_up_for_profile(start_dir: Path | None) -> Path | None:
    """Find the first ``optimizer.yaml`` from *start_dir* (or cwd) to the root."""
    current = (start_dir or Path.cwd()).expanduser()
    with contextlib.suppress(OSError):
        current = current.resolve()
    for directory in (current, *current.parents):
        candidate = directory / PROFILE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _discover_experiment_dirs(
    request: MigrationRequest, external_profiles: tuple[Path, ...], target_package: Path
) -> tuple[Path, ...]:
    """Explicit directories plus the default tree each affected profile reserves."""
    candidates: list[Path] = [Path(directory) for directory in request.experiment_dirs]
    for profile_dir in (*(profile.parent for profile in external_profiles), target_package):
        root = profile_dir.joinpath(*EXPERIMENT_DEFAULT_ROOT)
        if root.is_dir():
            candidates.extend(sorted(entry for entry in root.iterdir() if entry.is_dir()))
    return _resolve_unique(candidates)


def _resolve_unique(candidates: list[Path]) -> tuple[Path, ...]:
    """Resolve before deduplicating, so two spellings of one path count once."""
    unique: dict[Path, None] = {}
    for candidate in candidates:
        unique.setdefault(candidate.expanduser().resolve(), None)
    return tuple(unique)


# ---------------------------------------------------------------------------
# Legacy-literal scanning
# ---------------------------------------------------------------------------


def _legacy_occurrences(text: str) -> list[tuple[int, str]]:
    """Return ``(line number, term)`` for each pre-rename literal left in *text*."""
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        haystack = line.lower()
        for allowed in _ALLOWED_LEGACY_TERMS:
            haystack = haystack.replace(allowed, "\0" * len(allowed))
        for term in _BANNED_LEGACY_TERMS:
            lowered = term.lower()
            if lowered in haystack:
                found.append((lineno, term))
                haystack = haystack.replace(lowered, "\0" * len(lowered))
    return found


def _legacy_findings(root: Path, manifest: Manifest) -> list[str]:
    """List every unrewritten literal in a package, by path and line.

    Every text file is read, not only the contract file: a leftover reference in
    a packaged skill, an ``agent.yaml`` entry, or a package-local profile is just
    as much a broken pointer after the rename.
    """
    findings: list[str] = []
    for rel in manifest:
        for _, term in _legacy_occurrences(rel):
            findings.append(f"{rel}: path still names {term!r}")
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, term in _legacy_occurrences(text):
            findings.append(f"{rel}:{lineno}: {term!r}")
    return findings


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@dataclass
class _ProfilePlan:
    """One external ``optimizer.yaml`` and the rewrite it needs, if any."""

    path: Path
    data: dict[str, Any]
    expected: str | None = None
    rewritten: dict[str, Any] | None = None
    conflict: str | None = None

    @property
    def needs_rewrite(self) -> bool:
        return self.rewritten is not None


def _read_profile_mapping(path: Path) -> dict[str, Any]:
    """Load a profile as a YAML mapping, or raise a controlled error."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MigrationError(f"{path}: cannot be read as YAML ({exc})") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise MigrationError(f"{path}: the document root must be a YAML mapping")
    return payload


def _plan_profile_change(
    payload: dict[str, Any], plan: MigrationPlan, label: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(rewritten payload or None, expected ethos value)``.

    ``None`` for the rewritten payload means the profile is already in its final
    form. The expected value is what verification requires afterwards, so a
    write that lands the wrong path is caught rather than accepted for merely
    ending in the right filename.
    """
    has_old = LEGACY_PROFILE_KEY in payload
    has_new = ETHOS_PROFILE_KEY in payload
    if not has_old and not has_new:
        return None, None

    old_value = payload.get(LEGACY_PROFILE_KEY)
    new_value = payload.get(ETHOS_PROFILE_KEY)
    if has_old and not isinstance(old_value, str):
        raise MigrationError(f"{label}: {LEGACY_PROFILE_KEY!r} must be a string path, not {old_value!r}")
    if has_new and not isinstance(new_value, str):
        raise MigrationError(f"{label}: {ETHOS_PROFILE_KEY!r} must be a string path, not {new_value!r}")

    source_value = old_value if has_old else new_value
    assert isinstance(source_value, str)  # both branches above rejected non-strings
    rewritten_value = _rewrite_profile_value(source_value, plan, label)

    # A half-converted profile carries both keys. They agree when the old value
    # rewrites to the new one, which is the state a resumed migration leaves
    # behind; anything else is a divergence a rename must not silently resolve.
    if has_old and has_new and new_value != rewritten_value:
        raise MigrationError(
            f"{label}: {LEGACY_PROFILE_KEY} is {old_value!r} but {ETHOS_PROFILE_KEY} is "
            f"{new_value!r}; the two disagree, so keep one and rerun"
        )

    rewritten = _replace_profile_key(payload, rewritten_value)
    return (None if rewritten == payload else rewritten), rewritten_value


def _rewrite_profile_value(value: str, plan: MigrationPlan, label: str) -> str:
    """Rewrite the old package segment and contract filename inside a profile path."""
    rewritten = [
        ethos_fileset_name(plan.agent)
        if segment == f"{plan.agent}{LEGACY_PACKAGE_SUFFIX}"
        else ETHOS_FILENAME
        if segment == LEGACY_CONTRACT_FILENAME
        else segment
        for segment in value.split("/")
    ]
    result = "/".join(rewritten)
    if not result.endswith(ETHOS_FILENAME):
        raise MigrationError(
            f"{label}: {LEGACY_PROFILE_KEY} is {value!r}, which no rewrite rule turns into a path "
            f"ending in {ETHOS_FILENAME}. Point it at the agent's contract file and rerun"
        )
    return result


def _replace_profile_key(payload: dict[str, Any], value: str) -> dict[str, Any]:
    """Swap the old key for ``ethos`` in place, preserving every other key's order."""
    rewritten: dict[str, Any] = {}
    for key, existing in payload.items():
        if key == LEGACY_PROFILE_KEY:
            rewritten[ETHOS_PROFILE_KEY] = value
        elif key == ETHOS_PROFILE_KEY:
            # Already written when the old key came first. Otherwise this is the
            # only occurrence, and the rewritten value belongs at this position.
            rewritten.setdefault(ETHOS_PROFILE_KEY, value)
        else:
            rewritten[key] = existing
    return rewritten


def _write_profile(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _plan_external_profile(path: Path, plan: MigrationPlan) -> _ProfilePlan:
    try:
        payload = _read_profile_mapping(path)
        rewritten, expected = _plan_profile_change(payload, plan, str(path))
    except MigrationError as exc:
        return _ProfilePlan(path=path, data={}, conflict=str(exc))
    return _ProfilePlan(path=path, data=payload, expected=expected, rewritten=rewritten)


def _profile_matches(path: Path, expected: str | None) -> bool:
    """True when the profile is exactly in its final form.

    The old key must be absent rather than merely falsy, and the ``ethos`` value
    must equal the one value this migration computed for this profile.
    """
    try:
        payload = _read_profile_mapping(path)
    except MigrationError:
        return False
    if LEGACY_PROFILE_KEY in payload:
        return False
    actual = payload[ETHOS_PROFILE_KEY] if ETHOS_PROFILE_KEY in payload else None
    return actual == expected


def _profile_is_free_of_legacy_key(path: Path) -> bool:
    try:
        return LEGACY_PROFILE_KEY not in _read_profile_mapping(path)
    except MigrationError:
        return False


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Source:
    label: str
    root: Path
    manifest: Manifest


def _merge_sources(sources: list[_Source], dest: Path) -> None:
    """Copy the union of *sources* into *dest*, refusing a divergent shared path.

    A one-shot move cannot undo a discarded copy, so a shared path whose bytes
    differ stops the command instead of picking a winner.
    """
    chosen: dict[str, tuple[_Source, FileFingerprint]] = {}
    conflicts: list[str] = []
    for source in sources:
        for rel, fingerprint in source.manifest.items():
            previous = chosen.get(rel)
            if previous is None:
                chosen[rel] = (source, fingerprint)
                continue
            prior_source, prior_fingerprint = previous
            if prior_fingerprint != fingerprint:
                conflicts.append(
                    f"{rel}: {prior_source.label} has {prior_fingerprint.size} bytes, "
                    f"{source.label} has {fingerprint.size} bytes"
                )
    if conflicts:
        raise MigrationError(
            "the legacy sources disagree, so neither copy was modified. Reconcile these paths "
            "and rerun:\n  " + "\n  ".join(sorted(conflicts))
        )
    for rel, (source, _) in sorted(chosen.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(source.root / rel, target)


def _rename_contract(staged: Path, agent: str) -> None:
    """Rewrite the contract file in place under its final name."""
    legacy = staged / LEGACY_CONTRACT_FILENAME
    target = staged / ETHOS_FILENAME
    if legacy.is_file() and target.is_file():
        raise MigrationError(
            f"the legacy source holds both {LEGACY_CONTRACT_FILENAME} and {ETHOS_FILENAME}; keep one and rerun"
        )
    if not legacy.is_file():
        if target.is_file():
            return
        raise MigrationError(
            f"the legacy source holds neither {LEGACY_CONTRACT_FILENAME} nor {ETHOS_FILENAME}, so "
            "there is no contract file to migrate"
        )
    target.write_text(_rewrite_identity_region(legacy.read_text(encoding="utf-8"), agent), encoding="utf-8")
    legacy.unlink()


def _rewrite_identity_region(markdown: str, agent: str) -> str:
    """Rewrite only the text between the front matter and the first ``##`` heading.

    That region holds the H1 title and the template banner. ``parse_ethos``
    discards it, so no validated content changes.
    """
    front = _FRONT_MATTER_RE.match(markdown)
    if front is None:
        raise MigrationError(f"the contract file is missing YAML front matter, so {ETHOS_FILENAME} cannot be staged")
    body = markdown[front.end() :]
    first_section = _SECTION_RE.search(body)
    cut = first_section.start() if first_section else len(body)
    region = _LEGACY_TITLE_RE.sub("# Ethos:", body[:cut])
    region = region.replace(LEGACY_CONTRACT_FILENAME, ETHOS_FILENAME)
    region = region.replace(LEGACY_WRITER_SKILL, ETHOS_WRITER_SKILL)
    region = region.replace(f"{agent}{LEGACY_PACKAGE_SUFFIX}", ethos_fileset_name(agent))
    return markdown[: front.end()] + region + body[cut:]


def _rewrite_packaged_profiles(staged: Path, plan: MigrationPlan) -> None:
    """Convert every ``optimizer.yaml`` that travels inside the package.

    These are rewritten in the staged copy, never in the legacy source, so the
    old package stays byte-for-byte authoritative until the transaction commits.
    Doing it before the literal scan is what lets a package carrying its own
    profile migrate at all.
    """
    for path in sorted(staged.rglob(PROFILE_FILENAME)):
        label = f"{path.relative_to(staged).as_posix()} (inside the package)"
        payload = _read_profile_mapping(path)
        rewritten, _ = _plan_profile_change(payload, plan, label)
        if rewritten is not None:
            _write_profile(path, rewritten)


def _stage(sources: list[_Source], dest: Path, plan: MigrationPlan) -> Manifest:
    """Build and validate the target package in *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    _merge_sources(sources, dest)
    _rename_contract(dest, plan.agent)
    _rewrite_packaged_profiles(dest, plan)
    manifest = build_manifest(dest)
    findings = _legacy_findings(dest, manifest)
    if findings:
        raise MigrationError(
            "no rewrite rule covers these pre-rename references, so nothing was changed. Edit them "
            "in the legacy source and rerun:\n  " + "\n  ".join(findings)
        )
    _validate_contract(dest)
    return manifest


def _validate_contract(package: Path) -> None:
    contract = package / ETHOS_FILENAME
    if not contract.is_file():
        raise MigrationError(f"{package} has no {ETHOS_FILENAME}")
    try:
        parse_ethos(contract.read_text(encoding="utf-8"))
    except (EthosParseError, yaml.YAMLError, OSError, UnicodeError) as exc:
        raise MigrationError(f"{contract} does not parse as {ETHOS_FILENAME}: {exc}") from exc


# ---------------------------------------------------------------------------
# Active-work gates
# ---------------------------------------------------------------------------


def _blocking_jobs(plan: MigrationPlan, jobs: JobStore) -> list[str]:
    """Name every nonterminal Insights job analyzing this agent in this workspace."""
    blocking: list[str] = []
    for job in jobs.list_jobs(workspace=plan.workspace):
        if job.source != INSIGHTS_JOB_SOURCE or job.workspace != plan.workspace:
            continue
        if job.spec.get("agent") != plan.agent:
            continue
        if _is_terminal(job.status):
            continue
        blocking.append(f"Insights job {job.name!r} is {job.status}")
    return blocking


def _is_terminal(status: str) -> bool:
    """Terminal per the shared platform statuses. An unknown status is not terminal."""
    try:
        return PlatformJobStatus(status).is_terminal()
    except ValueError:
        return False


def _blocking_experiment_runs(plan: MigrationPlan) -> list[str]:
    """Name every experiment directory whose run may still be resumable.

    Candidate records are the durable evidence that a run owns state on disk.
    With records present, only an explicit ``completed`` status proceeds:
    anything else, including a missing status, an unrecognized one, and a
    ``run.json`` that is unreadable or not an object, is treated as live. That
    can reject a run that was not resumable, but it cannot let a resumable one
    through.
    """
    blocking: list[str] = []
    for directory in plan.experiment_dirs:
        state = directory / EXPERIMENT_STATE_DIRNAME
        candidates = sorted((state / "candidates").glob("*.json"))
        if not candidates:
            continue
        count = len(candidates)
        try:
            record = json.loads((state / "run.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            blocking.append(f"{directory} keeps {count} candidate record(s) but its run.json is missing or unreadable")
            continue
        if not isinstance(record, dict):
            blocking.append(f"{directory} keeps {count} candidate record(s) but its run.json is not an object")
            continue
        status = record.get("status")
        if status == COMPLETED_RUN_STATUS:
            continue
        described = "no status" if status is None else f"status {status!r}"
        blocking.append(f"{directory} holds a run with {described} and {count} candidate record(s)")
    return blocking


def _run_gates(plan: MigrationPlan, jobs: JobStore) -> tuple[list[str], list[str]]:
    """Run both active-work gates. They apply only when work is required."""
    job_blocks = _blocking_jobs(plan, jobs)
    run_blocks = _blocking_experiment_runs(plan)
    lines = [
        f"Insights job gate: {'blocked' if job_blocks else 'clear'}",
        f"Experimentalist run gate: {'blocked' if run_blocks else 'clear'}",
    ]
    return lines, [*job_blocks, *run_blocks]


# ---------------------------------------------------------------------------
# Transaction record
# ---------------------------------------------------------------------------

_STEPS = (
    "backups",
    "upload-target-fileset",
    "verify-target-fileset",
    "write-target-package",
    "rewrite-profiles",
    "delete-old-fileset",
    "delete-old-package",
    "final-verify",
)


def _journal_field(payload: dict[str, Any], name: str) -> Any:
    if name not in payload:
        raise ValueError(f"journal field {name!r} is missing")
    return payload[name]


def _journal_string(payload: dict[str, Any], name: str) -> str:
    value = _journal_field(payload, name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"journal field {name!r} must be a non-empty string")
    return value


def _journal_absolute_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    try:
        path = Path(value)
        normalized = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"{label} is not a valid path ({exc})") from exc
    if not path.is_absolute() or path != normalized:
        raise ValueError(f"{label} must be an absolute normalized path")
    return value


def _journal_optional_absolute_path(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _journal_absolute_path(value, label)


def _journal_string_list(payload: dict[str, Any], name: str) -> list[str]:
    value = _journal_field(payload, name)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"journal field {name!r} must be an array of strings")
    return value


def _journal_absolute_path_list(payload: dict[str, Any], name: str) -> list[str]:
    return [
        _journal_absolute_path(value, f"journal field {name!r}[{index}]")
        for index, value in enumerate(_journal_string_list(payload, name))
    ]


def _journal_external_profiles(payload: dict[str, Any]) -> dict[str, str | None]:
    value = _journal_field(payload, "external_profiles")
    if not isinstance(value, dict):
        raise ValueError("journal field 'external_profiles' must be an object")
    profiles: dict[str, str | None] = {}
    for raw_path, expected in value.items():
        path = _journal_absolute_path(raw_path, "journal external profile path")
        if expected is not None and not isinstance(expected, str):
            raise ValueError(f"journal external profile {path!r} must map to a string or null")
        profiles[path] = expected
    return profiles


def _journal_profile_backups(payload: dict[str, Any]) -> dict[str, str]:
    value = _journal_field(payload, "profile_backups")
    if not isinstance(value, dict):
        raise ValueError("journal field 'profile_backups' must be an object")
    backups: dict[str, str] = {}
    for raw_path, raw_backup in value.items():
        path = _journal_absolute_path(raw_path, "journal profile path")
        backups[path] = _journal_absolute_path(raw_backup, f"journal backup for {path!r}")
    return backups


@dataclass
class _TransactionRecord:
    """Every input and effect of one transaction, in memory and in the journal.

    Recovery reads only this. A later run may pass a different ``--agents-root``,
    ``--profile``, or ``--experiment-dir``, and none of it can redirect recovery
    at a path the failed run never touched.
    """

    workspace: str
    agent: str
    agents_root: str
    old_package: str
    target_package: str
    old_fileset: str
    target_fileset: str
    # Absolute path to the expected ``ethos`` value, or null when the profile
    # carries neither key and must stay untouched.
    external_profiles: dict[str, str | None]
    packaged_profiles: list[str]
    experiment_dirs: list[str]
    backup_root: str
    legacy_local_backup: str | None
    legacy_remote_backup: str | None
    profile_backups: dict[str, str]
    staged: Manifest
    old_local: Manifest | None
    old_remote: Manifest | None
    target_fileset_state: _TargetState
    target_package_state: _TargetState
    steps: list[str] = field(default_factory=list)
    failed_step: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "agent": self.agent,
            "agents_root": self.agents_root,
            "old_package": self.old_package,
            "target_package": self.target_package,
            "old_fileset": self.old_fileset,
            "target_fileset": self.target_fileset,
            "external_profiles": self.external_profiles,
            "packaged_profiles": self.packaged_profiles,
            "experiment_dirs": self.experiment_dirs,
            "backup_root": self.backup_root,
            "legacy_local_backup": self.legacy_local_backup,
            "legacy_remote_backup": self.legacy_remote_backup,
            "profile_backups": self.profile_backups,
            "staged": _manifest_to_json(self.staged),
            "old_local": _manifest_to_json(self.old_local),
            "old_remote": _manifest_to_json(self.old_remote),
            "target_fileset_state": self.target_fileset_state.value,
            "target_package_state": self.target_package_state.value,
            "steps": self.steps,
            "failed_step": self.failed_step,
        }

    @classmethod
    def from_json(cls, payload: object) -> _TransactionRecord:
        if not isinstance(payload, dict):
            raise ValueError("the journal root must be an object")
        data = cast(dict[str, Any], payload)

        workspace = _journal_string(data, "workspace")
        agent = _journal_string(data, "agent")
        try:
            validate_agent_name(agent)
        except MigrationError as exc:
            raise ValueError(f"journal field 'agent' is invalid ({exc})") from exc

        agents_root = _journal_absolute_path(_journal_field(data, "agents_root"), "journal field 'agents_root'")
        old_package = _journal_absolute_path(_journal_field(data, "old_package"), "journal field 'old_package'")
        target_package = _journal_absolute_path(
            _journal_field(data, "target_package"), "journal field 'target_package'"
        )
        old_fileset = _journal_string(data, "old_fileset")
        target_fileset = _journal_string(data, "target_fileset")
        if old_package != str(Path(agents_root) / f"{agent}{LEGACY_PACKAGE_SUFFIX}"):
            raise ValueError("journal field 'old_package' does not match its recorded agents root and agent")
        if target_package != str(Path(agents_root) / ethos_fileset_name(agent)):
            raise ValueError("journal field 'target_package' does not match its recorded agents root and agent")
        if old_fileset != f"{agent}{LEGACY_PACKAGE_SUFFIX}" or target_fileset != ethos_fileset_name(agent):
            raise ValueError("the journal Fileset names do not match its recorded agent")

        packaged_profiles = _journal_string_list(data, "packaged_profiles")
        if any(not _is_safe_relative_path(path) for path in packaged_profiles):
            raise ValueError("journal field 'packaged_profiles' contains an unsafe relative path")
        steps = _journal_string_list(data, "steps")
        if steps != list(_STEPS[: len(steps)]):
            raise ValueError("journal field 'steps' must be an ordered prefix of the transaction steps")
        failed_step = _journal_field(data, "failed_step")
        if failed_step is not None and (not isinstance(failed_step, str) or failed_step not in _STEPS):
            raise ValueError("journal field 'failed_step' must be a transaction step or null")
        try:
            target_fileset_state = _TargetState(_journal_string(data, "target_fileset_state"))
            target_package_state = _TargetState(_journal_string(data, "target_package_state"))
        except ValueError as exc:
            raise ValueError("the journal target state is not recognized") from exc

        staged = _manifest_from_json(_journal_field(data, "staged"), "journal field 'staged'")
        if staged is None:
            raise ValueError("journal field 'staged' cannot be null")
        old_local = _manifest_from_json(_journal_field(data, "old_local"), "journal field 'old_local'")
        old_remote = _manifest_from_json(_journal_field(data, "old_remote"), "journal field 'old_remote'")
        legacy_local_backup = _journal_optional_absolute_path(
            _journal_field(data, "legacy_local_backup"), "journal field 'legacy_local_backup'"
        )
        legacy_remote_backup = _journal_optional_absolute_path(
            _journal_field(data, "legacy_remote_backup"), "journal field 'legacy_remote_backup'"
        )
        if (old_local is None) != (legacy_local_backup is None):
            raise ValueError("journal fields 'old_local' and 'legacy_local_backup' must agree")
        if (old_remote is None) != (legacy_remote_backup is None):
            raise ValueError("journal fields 'old_remote' and 'legacy_remote_backup' must agree")

        return cls(
            workspace=workspace,
            agent=agent,
            agents_root=agents_root,
            old_package=old_package,
            target_package=target_package,
            old_fileset=old_fileset,
            target_fileset=target_fileset,
            external_profiles=_journal_external_profiles(data),
            packaged_profiles=packaged_profiles,
            experiment_dirs=_journal_absolute_path_list(data, "experiment_dirs"),
            backup_root=_journal_absolute_path(_journal_field(data, "backup_root"), "journal field 'backup_root'"),
            legacy_local_backup=legacy_local_backup,
            legacy_remote_backup=legacy_remote_backup,
            profile_backups=_journal_profile_backups(data),
            staged=staged,
            old_local=old_local,
            old_remote=old_remote,
            target_fileset_state=target_fileset_state,
            target_package_state=target_package_state,
            steps=steps,
            failed_step=failed_step,
        )

    def next_step(self) -> str:
        completed = set(self.steps)
        return next((name for name in _STEPS if name not in completed), _STEPS[-1])


# ---------------------------------------------------------------------------
# Assessment: discover, read, stage, classify, gate
# ---------------------------------------------------------------------------


@dataclass
class _Assessment:
    """Transient state the apply sequence needs beyond the durable record."""

    plan: MigrationPlan
    staged_dir: Path
    staged: Manifest
    old_local: Manifest | None
    old_remote: Manifest | None
    target_local: Manifest | None
    target_remote: Manifest | None
    profiles: list[_ProfilePlan]


def _read_fileset(
    store: FilesetStore, workspace: str, name: str, stack: contextlib.ExitStack
) -> tuple[Manifest, Path] | None:
    """Download a Fileset into a temporary directory and fingerprint it."""
    if not store.exists(workspace=workspace, name=name):
        return None
    dest = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=f".ethos-migrate-{name}-")))
    store.download(workspace=workspace, name=name, dest=dest)
    return build_manifest(dest), dest


def _assess(
    plan: MigrationPlan,
    filesets: FilesetStore,
    jobs: JobStore,
    stack: contextlib.ExitStack,
) -> tuple[Outcome, list[str], _Assessment | None]:
    """Classify the current state, staging and gating as the state table requires."""
    lines = _location_lines(plan)

    old_local = _package_manifest(plan.old_package)
    target_local = _package_manifest(plan.target_package)
    old_remote_read = _read_fileset(filesets, plan.workspace, plan.old_fileset, stack)
    target_remote_read = _read_fileset(filesets, plan.workspace, plan.target_fileset, stack)
    old_remote = old_remote_read[0] if old_remote_read is not None else None
    target_remote = target_remote_read[0] if target_remote_read is not None else None

    profiles = [_plan_external_profile(path, plan) for path in plan.external_profiles]
    conflicts = [profile.conflict for profile in profiles if profile.conflict is not None]
    if conflicts:
        return (
            Outcome.CONFLICT,
            [*lines, "Conflict: affected profiles disagree; nothing was changed.", *(f"  {c}" for c in conflicts)],
            None,
        )

    legacy_present = old_local is not None or old_remote is not None
    target_present = target_local is not None or target_remote is not None
    pending_profiles = [profile.path for profile in profiles if profile.needs_rewrite]
    lines += [
        f"Legacy local package: {'present' if old_local is not None else 'absent'}",
        f"Legacy Fileset: {'present' if old_remote is not None else 'absent'}",
        f"Target local package: {'present' if target_local is not None else 'absent'}",
        f"Target Fileset: {'present' if target_remote is not None else 'absent'}",
        f"External profiles still naming the pre-rename artifact: {len(pending_profiles)}",
    ]

    staged_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".ethos-migrate-staged-"))) / "package"
    staged: Manifest | None = None
    if legacy_present:
        sources: list[_Source] = []
        if old_local is not None:
            sources.append(_Source("the local package", plan.old_package, old_local))
        if old_remote_read is not None:
            sources.append(_Source("the Fileset", old_remote_read[1], old_remote_read[0]))
        staged = _stage(sources, staged_dir, plan)

    target_complete = _target_is_complete(plan, target_local, target_remote)

    if not legacy_present and not target_present:
        if pending_profiles:
            return (
                Outcome.CONFLICT,
                [
                    *lines,
                    "Conflict: no legacy source and no target exist, but these profiles still name "
                    "the pre-rename artifact. Fix or remove each one, then rerun.",
                    *(f"  {path}" for path in pending_profiles),
                ],
                None,
            )
        return Outcome.NOTHING_TO_MIGRATE, [*lines, "Nothing to migrate."], None

    if legacy_present:
        if target_present and not (target_complete and target_local == staged):
            return (
                Outcome.CONFLICT,
                [
                    *lines,
                    "Conflict: a target exists but is partial, or does not match the staged output. "
                    "Reconcile it by hand, then rerun; nothing was changed.",
                ],
                None,
            )
    else:
        if not target_complete:
            return (
                Outcome.CONFLICT,
                [
                    *lines,
                    "Conflict: the target is partial, divergent, or still names the pre-rename "
                    "artifact, and no legacy source or journal explains it. Reconcile it by hand, "
                    "then rerun; nothing was changed.",
                ],
                None,
            )
        if not pending_profiles:
            return Outcome.ALREADY_MIGRATED, [*lines, "Already migrated. Nothing to do."], None
        # Stage from the verified target so resuming profile conversion runs
        # through the same apply sequence a full migration does.
        _copy_tree(plan.target_package, staged_dir)
        staged = build_manifest(staged_dir)

    assert staged is not None  # every branch above either returned or staged
    gate_lines, blocking = _run_gates(plan, jobs)
    lines += gate_lines
    if blocking:
        return (
            Outcome.BLOCKED,
            [
                *lines,
                "Blocked: active work would break under a rename. Let it finish or cancel it, then rerun.",
                *(f"  {reason}" for reason in blocking),
            ],
            None,
        )

    return (
        Outcome.PENDING,
        lines,
        _Assessment(
            plan=plan,
            staged_dir=staged_dir,
            staged=staged,
            old_local=old_local,
            old_remote=old_remote,
            target_local=target_local,
            target_remote=target_remote,
            profiles=profiles,
        ),
    )


def _package_manifest(package: Path) -> Manifest | None:
    """Fingerprint a package root, or return None when it is absent."""
    if package.is_symlink():
        raise MigrationError(
            f"{package} is a symlink; migration copies, uploads, and deletes this path, so "
            "following it could reach content outside the agents root. Replace it with a real directory"
        )
    if not package.is_dir():
        return None
    return build_manifest(package)


def _target_is_complete(plan: MigrationPlan, target_local: Manifest | None, target_remote: Manifest | None) -> bool:
    """True when both target copies exist, match, parse, and carry no old literal."""
    if target_local is None or target_remote is None or target_local != target_remote:
        return False
    if _legacy_findings(plan.target_package, target_local):
        return False
    try:
        _validate_contract(plan.target_package)
    except MigrationError:
        return False
    return True


def _location_lines(plan: MigrationPlan) -> list[str]:
    """Every location the command reads or writes, for the dry-run report."""
    return [
        f"Agent: {plan.agent}   Workspace: {plan.workspace}",
        f"Local package: {plan.old_package} -> {plan.target_package}",
        f"Fileset: {plan.old_fileset} -> {plan.target_fileset}",
        f"Journal: {journal_dir(plan.workspace, plan.agent)}",
        f"External profiles rewritten in place ({len(plan.external_profiles)}):",
        *(f"  {path}" for path in plan.external_profiles),
        f"Package-local profiles rewritten inside the target package ({len(plan.packaged_profiles)}):",
        *(f"  {plan.target_package / rel}" for rel in plan.packaged_profiles),
        f"Known experiment directories ({len(plan.experiment_dirs)}):",
        *(f"  {path}" for path in plan.experiment_dirs),
        "Custom profiles and experiment directories outside this set cannot be discovered, because "
        "the command performs no global scan. Pass each one with --profile or --experiment-dir.",
    ]


# ---------------------------------------------------------------------------
# Locking and journal
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _exclusive_lock(directory: Path, workspace: str, agent: str) -> Iterator[None]:
    """Hold a non-blocking exclusive lock across discovery and the whole apply.

    The kernel releases the lock when the process exits, cleanly or not, so no
    stale lock record ever needs cleaning.
    """
    descriptor = os.open(directory / "lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MigrationError(
                f"another ethos migrate is already running for agent {agent!r} in workspace "
                f"{workspace!r}; nothing was read or written"
            ) from exc
        yield
    finally:
        os.close(descriptor)


def _write_journal(directory: Path, payload: dict[str, Any]) -> None:
    """Replace the journal atomically, so a crash never leaves a half-written record."""
    temporary = directory / f"{JOURNAL_FILENAME}.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, directory / JOURNAL_FILENAME)


def _persist_best_effort(directory: Path, record: _TransactionRecord) -> None:
    """Write the journal without letting a write failure mask the real error."""
    try:
        _write_journal(directory, record.to_json())
    except Exception:
        logger.exception("Could not persist the ethos migration journal under %s", directory)


def _discard_transaction_state(directory: Path, backups: Path) -> None:
    """Remove the journal before its backups. The lock file stays."""
    journal = directory / JOURNAL_FILENAME
    try:
        journal.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RecoveryRequired(
            f"the migration finished but its journal at {journal} could not be removed ({exc}); "
            f"status is recovery-required. All backups under {backups} were kept"
        ) from exc
    shutil.rmtree(backups, ignore_errors=True)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _apply(
    assessment: _Assessment,
    *,
    directory: Path,
    filesets: FilesetStore,
    lines: list[str],
) -> MigrationReport:
    """Run the compensating transaction.

    Every step before ``final-verify`` leaves the old local package, the old
    Fileset, and the old profile keys authoritative, so a failure anywhere can be
    undone from the in-memory record and the backups. The journal is a durable
    copy of that record, never the thing compensation depends on.
    """
    plan = assessment.plan
    backups = directory / "backup"
    record = _TransactionRecord(
        workspace=plan.workspace,
        agent=plan.agent,
        agents_root=str(plan.agents_root),
        old_package=str(plan.old_package),
        target_package=str(plan.target_package),
        old_fileset=plan.old_fileset,
        target_fileset=plan.target_fileset,
        external_profiles={str(profile.path): profile.expected for profile in assessment.profiles},
        packaged_profiles=list(plan.packaged_profiles),
        experiment_dirs=[str(path) for path in plan.experiment_dirs],
        backup_root=str(backups),
        legacy_local_backup=str(backups / "legacy-local") if assessment.old_local is not None else None,
        legacy_remote_backup=str(backups / "legacy-remote") if assessment.old_remote is not None else None,
        profile_backups={},
        staged=assessment.staged,
        old_local=assessment.old_local,
        old_remote=assessment.old_remote,
        target_fileset_state=(
            _TargetState.PRE_EXISTING if assessment.target_remote is not None else _TargetState.ABSENT
        ),
        target_package_state=(
            _TargetState.PRE_EXISTING if assessment.target_local is not None else _TargetState.ABSENT
        ),
    )

    def persist() -> None:
        _write_journal(directory, record.to_json())

    def finish(name: str) -> None:
        record.steps.append(name)
        persist()

    try:
        persist()

        _build_backups(assessment, record, backups, filesets)
        finish("backups")

        if assessment.target_remote is None:
            record.target_fileset_state = _TargetState.CREATING
            persist()
            # Conditional create is the ownership decision: a false return means
            # another writer created the Fileset between assessment and now, and
            # this transaction must never delete a Fileset it did not create.
            if not filesets.create(workspace=plan.workspace, name=plan.target_fileset):
                record.target_fileset_state = _TargetState.PRE_EXISTING
                persist()
                raise MigrationError(
                    f"Fileset {plan.workspace}/{plan.target_fileset} appeared while this migration "
                    "was running, so it belongs to another writer"
                )
            record.target_fileset_state = _TargetState.OWNED
            persist()
            filesets.upload(workspace=plan.workspace, name=plan.target_fileset, source=assessment.staged_dir)
        finish("upload-target-fileset")

        _verify_remote(filesets, plan.workspace, plan.target_fileset, record.staged)
        finish("verify-target-fileset")

        if assessment.target_local is None:
            record.target_package_state = _TargetState.CREATING
            persist()
            # No pre-clean: a path that appeared after assessment must break this
            # transaction rather than be replaced.
            try:
                _copy_tree(assessment.staged_dir, plan.target_package)
            except FileExistsError as exc:
                record.target_package_state = _TargetState.PRE_EXISTING
                persist()
                raise MigrationError(
                    f"{plan.target_package} appeared while this migration was running, so it belongs to another writer"
                ) from exc
            record.target_package_state = _TargetState.OWNED
            persist()
        finish("write-target-package")

        _rewrite_profiles(assessment, record)
        finish("rewrite-profiles")

        if assessment.old_remote is not None:
            filesets.delete(workspace=plan.workspace, name=plan.old_fileset)
        finish("delete-old-fileset")

        if assessment.old_local is not None:
            _remove_tree(plan.old_package)
        finish("delete-old-package")

        _verify_final(record, filesets)
        finish("final-verify")
    except Exception as exc:
        failed = record.next_step()
        record.failed_step = failed
        # Compensate from the in-memory record before touching the journal: a
        # journal write is exactly what may have just failed, and a second
        # failure here must not skip the undo.
        try:
            _compensate(record, filesets)
        except Exception as compensation_error:
            _persist_best_effort(directory, record)
            raise RecoveryRequired(
                f"ethos migrate failed at step {failed!r} and could not undo its own work "
                f"({compensation_error}); status is recovery-required. The journal and backups "
                f"under {directory} are kept, and the next run recovers before any new work"
            ) from compensation_error
        _discard_transaction_state(directory, backups)
        raise MigrationError(
            f"ethos migrate failed at step {failed!r} ({exc}); the old local package, the old "
            "Fileset, and the old profile keys were restored and remain authoritative"
        ) from exc

    _discard_transaction_state(directory, backups)
    return MigrationReport(outcome=Outcome.MIGRATED, lines=[*lines, "Migrated."])


def _build_backups(assessment: _Assessment, record: _TransactionRecord, backups: Path, filesets: FilesetStore) -> None:
    """Copy every legacy source and external profile, then verify each by checksum."""
    plan = assessment.plan
    backups.mkdir(parents=True, exist_ok=True)

    if record.legacy_local_backup is not None:
        destination = Path(record.legacy_local_backup)
        shutil.rmtree(destination, ignore_errors=True)
        _copy_tree(plan.old_package, destination)
        if build_manifest(destination) != assessment.old_local:
            raise MigrationError(f"the backup of {plan.old_package} does not match its source")

    if record.legacy_remote_backup is not None:
        destination = Path(record.legacy_remote_backup)
        shutil.rmtree(destination, ignore_errors=True)
        filesets.download(workspace=plan.workspace, name=plan.old_fileset, dest=destination)
        if build_manifest(destination) != assessment.old_remote:
            raise MigrationError(f"the backup of Fileset {plan.old_fileset!r} does not match its source")

    profile_backups = backups / "profiles"
    profile_backups.mkdir(parents=True, exist_ok=True)
    for index, profile in enumerate(assessment.profiles):
        destination = profile_backups / f"{index:03d}-{profile.path.name}"
        _copy_file(profile.path, destination)
        if _fingerprint(destination) != _fingerprint(profile.path):
            raise MigrationError(f"the backup of {profile.path} does not match its source")
        record.profile_backups[str(profile.path)] = str(destination)


def _rewrite_profiles(assessment: _Assessment, record: _TransactionRecord) -> None:
    for profile in assessment.profiles:
        if profile.rewritten is not None:
            _write_profile(profile.path, profile.rewritten)
    for raw_path, expected in record.external_profiles.items():
        if not _profile_matches(Path(raw_path), expected):
            raise MigrationError(f"{raw_path} does not hold {ETHOS_PROFILE_KEY}: {expected!r} after the rewrite")


def _verify_remote(filesets: FilesetStore, workspace: str, name: str, expected: Manifest) -> None:
    """Download the Fileset and compare manifests, because the list API has no checksum."""
    with tempfile.TemporaryDirectory(prefix=f".ethos-migrate-verify-{name}-") as tmp:
        dest = Path(tmp)
        filesets.download(workspace=workspace, name=name, dest=dest)
        actual = build_manifest(dest)
    if actual != expected:
        raise MigrationError(f"Fileset {workspace}/{name} does not match the expected manifest")


def _remote_matches(filesets: FilesetStore, workspace: str, name: str, expected: Manifest) -> bool:
    if not filesets.exists(workspace=workspace, name=name):
        return False
    try:
        _verify_remote(filesets, workspace, name, expected)
    except MigrationError:
        return False
    return True


def _verify_final(record: _TransactionRecord, filesets: FilesetStore) -> None:
    """Confirm the complete final target and the converted profiles before committing."""
    target_package = Path(record.target_package)
    if build_manifest(target_package) != record.staged:
        raise MigrationError(f"{target_package} does not match the staged package")
    _validate_contract(target_package)
    findings = _legacy_findings(target_package, record.staged)
    if findings:
        raise MigrationError(f"{target_package} still names the pre-rename artifact: {findings}")
    _verify_remote(filesets, record.workspace, record.target_fileset, record.staged)
    for rel in record.packaged_profiles:
        packaged = target_package / rel
        if packaged.is_file() and not _profile_is_free_of_legacy_key(packaged):
            raise MigrationError(f"{packaged} still names the pre-rename artifact")
    for raw_path, expected in record.external_profiles.items():
        if not _profile_matches(Path(raw_path), expected):
            raise MigrationError(f"{raw_path} does not hold {ETHOS_PROFILE_KEY}: {expected!r}")
    if Path(record.old_package).exists():
        raise MigrationError(f"{record.old_package} still exists")
    if filesets.exists(workspace=record.workspace, name=record.old_fileset):
        raise MigrationError(f"Fileset {record.workspace}/{record.old_fileset} still exists")


# ---------------------------------------------------------------------------
# Compensation and recovery
# ---------------------------------------------------------------------------


def _remote_manifest(filesets: FilesetStore, workspace: str, name: str) -> Manifest | None:
    if not filesets.exists(workspace=workspace, name=name):
        return None
    with tempfile.TemporaryDirectory(prefix=f".ethos-migrate-recover-{name}-") as tmp:
        destination = Path(tmp)
        filesets.download(workspace=workspace, name=name, dest=destination)
        return build_manifest(destination)


def _manifest_is_compatible_subset(actual: Manifest, expected: Manifest) -> bool:
    return all(expected.get(path) == fingerprint for path, fingerprint in actual.items())


def _remove_local_target_if_owned(record: _TransactionRecord) -> str | None:
    target = Path(record.target_package)
    if record.target_package_state is _TargetState.PRE_EXISTING:
        return None
    if not target.exists() and not target.is_symlink():
        return None
    if record.target_package_state is _TargetState.ABSENT:
        return (
            f"cannot prove that local target {target} belongs to this transaction because the journal "
            "records no creation attempt; the target was preserved"
        )
    try:
        actual = build_manifest(target)
    except (MigrationError, OSError) as exc:
        return f"cannot prove that local target {target} belongs to this transaction ({exc}); the target was preserved"
    if actual != record.staged:
        return (
            f"cannot prove that local target {target} belongs to this transaction because its manifest "
            "differs from the recorded target manifest; the target was preserved"
        )
    _remove_tree(target)
    return None


def _remove_fileset_target_if_owned(record: _TransactionRecord, filesets: FilesetStore) -> str | None:
    if record.target_fileset_state is _TargetState.PRE_EXISTING:
        return None
    try:
        actual = _remote_manifest(filesets, record.workspace, record.target_fileset)
    except Exception as exc:
        return (
            f"cannot prove that Fileset {record.workspace}/{record.target_fileset} belongs to this transaction "
            f"because its manifest could not be read ({exc}); the Fileset was preserved"
        )
    if actual is None:
        return None
    if record.target_fileset_state is _TargetState.ABSENT:
        return (
            f"cannot prove that Fileset {record.workspace}/{record.target_fileset} belongs to this transaction "
            "because the journal records no creation attempt; the Fileset was preserved"
        )

    created_but_not_recorded = record.target_fileset_state is _TargetState.CREATING and (
        actual == {} or actual == record.staged
    )
    recorded_as_owned = record.target_fileset_state is _TargetState.OWNED and _manifest_is_compatible_subset(
        actual, record.staged
    )
    if not created_but_not_recorded and not recorded_as_owned:
        return (
            f"cannot prove that Fileset {record.workspace}/{record.target_fileset} belongs to this transaction "
            "because its manifest differs from every recorded transaction state; the Fileset was preserved"
        )
    filesets.delete(workspace=record.workspace, name=record.target_fileset)
    return None


def _restore_local_tree(source: Path, destination: Path, expected: Manifest) -> None:
    """Restore a missing or compatible partial tree without overwriting divergence."""
    if destination.is_symlink():
        raise MigrationError(f"{destination} is a symlink, so the legacy package cannot be restored safely")
    if destination.is_dir() and build_manifest(destination) == expected:
        return
    if build_manifest(source) != expected:
        raise MigrationError(f"the local backup at {source} does not match the recorded legacy manifest")
    if not destination.exists():
        _copy_tree(source, destination)
        return
    if not destination.is_dir():
        raise MigrationError(f"{destination} exists but is not a directory, so the legacy package was preserved")

    actual = build_manifest(destination)
    divergent = [path for path, fingerprint in actual.items() if expected.get(path) != fingerprint]
    if divergent:
        raise MigrationError(
            f"{destination} contains divergent legacy paths, so recovery preserved it: {', '.join(divergent)}"
        )
    for rel in sorted(expected.keys() - actual.keys()):
        target = destination / rel
        if target.exists() or target.is_symlink():
            raise MigrationError(f"{target} appeared during recovery, so it was preserved")
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(source / rel, target)


def _undo(record: _TransactionRecord, filesets: FilesetStore) -> None:
    """Undo this transaction's writes from the record and the backups.

    Each action is conditional on current state, so re-running it after a partial
    compensation is safe. A target is deleted only when its recorded operation
    state and manifest prove that this transaction created it.
    """
    for raw_path, raw_backup in record.profile_backups.items():
        backup = Path(raw_backup)
        if backup.is_file():
            _copy_file(backup, Path(raw_path))

    ambiguities = [
        message
        for message in (
            _remove_local_target_if_owned(record),
            _remove_fileset_target_if_owned(record, filesets),
        )
        if message is not None
    ]

    old_package = Path(record.old_package)
    if record.legacy_local_backup is not None and record.old_local is not None:
        _restore_local_tree(Path(record.legacy_local_backup), old_package, record.old_local)
    if record.legacy_remote_backup is not None and record.old_remote is not None:
        # Converge rather than only fill a gap: a compensation that created the
        # Fileset and then failed to upload leaves it empty, and the next attempt
        # has to be able to finish that restore.
        if not _remote_matches(filesets, record.workspace, record.old_fileset, record.old_remote):
            if not filesets.exists(workspace=record.workspace, name=record.old_fileset):
                filesets.create(workspace=record.workspace, name=record.old_fileset)
            filesets.upload(
                workspace=record.workspace,
                name=record.old_fileset,
                source=Path(record.legacy_remote_backup),
            )
    if ambiguities:
        raise MigrationError("; ".join(ambiguities))


def _compensate(record: _TransactionRecord, filesets: FilesetStore) -> None:
    """Undo the failed transaction, then verify the old state is authoritative again."""
    _undo(record, filesets)

    old_package = Path(record.old_package)
    if record.old_local is not None and build_manifest(old_package) != record.old_local:
        raise MigrationError(f"{old_package} was not restored to its original contents")
    if record.old_remote is not None:
        _verify_remote(filesets, record.workspace, record.old_fileset, record.old_remote)
    for raw_path, raw_backup in record.profile_backups.items():
        if _fingerprint(Path(raw_path)) != _fingerprint(Path(raw_backup)):
            raise MigrationError(f"{raw_path} was not restored to its original contents")


def _recover(directory: Path, filesets: FilesetStore) -> MigrationReport:
    """Finish or undo the transaction the journal describes, before any new work.

    Only the journal is read. Whatever ``--agents-root``, ``--profile``, or
    ``--experiment-dir`` this invocation passed is ignored until recovery ends,
    so recovery can never write to a path the failed run never touched.
    """
    try:
        record = _TransactionRecord.from_json(json.loads((directory / JOURNAL_FILENAME).read_text(encoding="utf-8")))
        backups = Path(record.backup_root)
        if backups != (directory / "backup").resolve():
            raise ValueError("journal field 'backup_root' does not match its transaction directory")
        recorded_backups = [
            path
            for path in (
                record.legacy_local_backup,
                record.legacy_remote_backup,
                *record.profile_backups.values(),
            )
            if path is not None
        ]
        if any(not Path(path).is_relative_to(backups) for path in recorded_backups):
            raise ValueError("a journal backup path escapes its recorded backup root")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError, AssertionError) as exc:
        raise RecoveryRequired(
            f"the journal under {directory} could not be read ({exc}); status is recovery-required. "
            "Inspect it by hand, because migration cannot tell what the interrupted run had done"
        ) from exc

    legacy_gone = not Path(record.old_package).exists() and not filesets.exists(
        workspace=record.workspace, name=record.old_fileset
    )
    if legacy_gone and _target_is_committed(record, filesets):
        _discard_transaction_state(directory, backups)
        return MigrationReport(
            outcome=Outcome.RECOVERED,
            lines=[
                f"Recovered: the interrupted migration of {record.agent!r} had already committed, so "
                "only cleanup remained. The target is authoritative.",
            ],
        )

    try:
        _compensate(record, filesets)
    except Exception as exc:
        _persist_best_effort(directory, record)
        raise RecoveryRequired(
            f"recovery of the interrupted migration of {record.agent!r} failed ({exc}); status is "
            f"recovery-required. The journal and backups under {directory} are kept"
        ) from exc

    _discard_transaction_state(directory, backups)
    return MigrationReport(
        outcome=Outcome.RECOVERED,
        lines=[
            f"Recovered: undid the interrupted migration of {record.agent!r}, which failed at step "
            f"{record.failed_step!r}. The pre-rename state is authoritative again; rerun to migrate.",
        ],
    )


def _target_is_committed(record: _TransactionRecord, filesets: FilesetStore) -> bool:
    """True when the interrupted transaction had already reached its commit point."""
    try:
        _verify_final(record, filesets)
    except MigrationError:
        return False
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_migration(
    request: MigrationRequest,
    *,
    filesets: FilesetStore,
    jobs: JobStore,
) -> MigrationReport:
    """Migrate one agent's Ethos artifacts, or report why it cannot.

    Args:
        request: The agent, workspace, roots, and caller-named paths.
        filesets: Fileset port.
        jobs: Platform Jobs port.

    Returns:
        A report whose ``outcome`` names the state-table row that applied.

    Raises:
        MigrationError: An invalid request, a lock held by another run, or a
            controlled failure whose old state was restored and remains
            authoritative.
        RecoveryRequired: Compensation failed. The journal and backups are kept,
            and the next run recovers before any new work.
    """
    validate_agent_name(request.agent)
    request = _normalize_request(request)
    directory = journal_dir(request.workspace, request.agent)

    if request.dry_run:
        return _dry_run(request, directory, filesets, jobs)

    # An empty state has nothing to lock against, and creating the lock file
    # would make a read-only no-op write to disk. This preliminary pass may
    # therefore return only that one outcome; every path that can mutate falls
    # through and repeats the whole discovery under the lock.
    if _is_empty_state(request, directory, filesets):
        return MigrationReport(
            outcome=Outcome.NOTHING_TO_MIGRATE,
            lines=[
                f"Nothing to migrate for agent {request.agent!r} in workspace {request.workspace!r}: "
                "no pre-rename package or Fileset, no target, and no profile naming the old artifact. "
                "Nothing was read beyond that check, and nothing was written.",
            ],
        )

    directory.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(directory, request.workspace, request.agent):
        if (directory / JOURNAL_FILENAME).is_file():
            return _recover(directory, filesets)
        # Authoritative discovery happens here, inside the lock, so nothing
        # planned below was read before a competing apply could be excluded.
        plan = _build_plan(request)
        with contextlib.ExitStack() as stack:
            outcome, lines, assessment = _classify(plan, filesets, jobs, stack)
            if assessment is None:
                return MigrationReport(outcome=outcome, lines=lines)
            return _apply(assessment, directory=directory, filesets=filesets, lines=lines)


def _dry_run(request: MigrationRequest, directory: Path, filesets: FilesetStore, jobs: JobStore) -> MigrationReport:
    """Report what an apply would do. Reads only; writes nothing anywhere."""
    prefix = "Dry run — nothing was written."
    if (directory / JOURNAL_FILENAME).is_file():
        return MigrationReport(
            outcome=Outcome.RECOVERY_REQUIRED,
            lines=[
                prefix,
                f"An interrupted migration of {request.agent!r} left a journal at {directory}.",
                "Recovery must finish before any new work. Rerun without --dry-run, which recovers "
                "first and then reports what remains.",
            ],
        )
    plan = _build_plan(request)
    with contextlib.ExitStack() as stack:
        outcome, lines, _ = _classify(plan, filesets, jobs, stack)
    if outcome is Outcome.PENDING:
        lines = [*lines, "Migration is required. Rerun without --dry-run to apply it."]
    return MigrationReport(outcome=outcome, lines=[prefix, *lines])


def _is_empty_state(request: MigrationRequest, directory: Path, filesets: FilesetStore) -> bool:
    """True when no journal, package, Fileset, or stale profile reference exists."""
    if (directory / JOURNAL_FILENAME).exists():
        return False
    plan = _build_plan(request)
    if plan.old_package.exists() or plan.target_package.exists():
        return False
    for name in (plan.old_fileset, plan.target_fileset):
        if filesets.exists(workspace=plan.workspace, name=name):
            return False
    return not any(_plan_external_profile(path, plan).needs_rewrite for path in plan.external_profiles)


def _classify(
    plan: MigrationPlan,
    filesets: FilesetStore,
    jobs: JobStore,
    stack: contextlib.ExitStack,
) -> tuple[Outcome, list[str], _Assessment | None]:
    """Assess the state, reporting a pre-write failure as a conflict rather than raising.

    Everything :func:`_assess` rejects — a symlink, divergent legacy sources, an
    unrewritable literal, an unparseable contract — happens before any write, so
    it belongs in the same "stop and explain" channel as a state conflict.
    """
    try:
        return _assess(plan, filesets, jobs, stack)
    except MigrationError as exc:
        return Outcome.CONFLICT, [*_location_lines(plan), f"Conflict: {exc}"], None
