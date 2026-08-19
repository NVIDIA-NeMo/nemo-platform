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

The apply path is a compensating transaction journalled outside the repository.
Its binding rule: **every controlled failure before the final verification
leaves the old local package, the old Fileset, and the old profile keys
authoritative.**

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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

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

INSIGHTS_JOB_SOURCE = "insights"
EXPERIMENT_STATE_DIRNAME = "eval-and-optimize"
EXPERIMENT_DEFAULT_ROOT = (".nemo-optimizer", "experiments")
BLOCKING_RUN_STATUSES = frozenset({"running", "failed"})

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
    CONFLICT = "conflict"
    BLOCKED = "blocked"


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
        """False for a conflict or a blocked run, which the CLI turns into exit 1."""
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

    Symlinks and paths that escape *root* are rejected rather than skipped: the
    Fileset upload follows a symlink and ships its target's bytes, so skipping
    one would move content from outside the package and hide it from every
    comparison this module makes.
    """
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


def _manifest_to_json(manifest: Manifest) -> dict[str, dict[str, Any]]:
    return {rel: {"size": fp.size, "sha256": fp.sha256} for rel, fp in manifest.items()}


def _manifest_from_json(payload: dict[str, dict[str, Any]]) -> Manifest:
    return {rel: FileFingerprint(size=entry["size"], sha256=entry["sha256"]) for rel, entry in payload.items()}


# ---------------------------------------------------------------------------
# Platform ports
# ---------------------------------------------------------------------------


class FilesetStore(Protocol):
    """The four Fileset operations migration needs.

    The list API carries no checksum, so remote bytes are verified by
    downloading them and computing the same local manifest.
    """

    def exists(self, *, workspace: str, name: str) -> bool: ...

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

    def download(self, *, workspace: str, name: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self.sdk.files.download(local_path=str(dest), fileset=name, workspace=workspace)

    def upload(self, *, workspace: str, name: str, source: Path) -> None:
        from nemo_agents_plugin.jobs.fileset_io import upload_to_fileset

        upload_to_fileset(source, fileset=name, workspace=workspace, sdk=self.sdk)

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
# Plan and journal locations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationPlan:
    """Every location this invocation may read or write."""

    agent: str
    workspace: str
    old_package: Path
    target_package: Path
    old_fileset: str
    target_fileset: str
    profiles: tuple[Path, ...]
    experiment_dirs: tuple[Path, ...]


def journal_dir(workspace: str, agent: str) -> Path:
    """Transaction directory for one workspace-and-agent pair, outside the repository.

    The pair is hashed with a NUL separator so ``("a", "b-c")`` and ``("a-b", "c")``
    cannot collide, and ``--agents-root`` never moves the journal into a checkout
    where a crashed migration could land in a commit.
    """
    digest = hashlib.sha256(f"{workspace}\0{agent}".encode()).hexdigest()
    return nmp_user_data_dir() / JOURNAL_ROOT_NAME / digest


def _build_plan(request: MigrationRequest) -> MigrationPlan:
    agents_root = Path(request.agents_root)
    old_package = agents_root / f"{request.agent}{LEGACY_PACKAGE_SUFFIX}"
    target_package = agents_root / ethos_fileset_name(request.agent)
    profiles = _discover_profiles(request, old_package, target_package)
    return MigrationPlan(
        agent=request.agent,
        workspace=request.workspace,
        old_package=old_package,
        target_package=target_package,
        old_fileset=f"{request.agent}{LEGACY_PACKAGE_SUFFIX}",
        target_fileset=ethos_fileset_name(request.agent),
        profiles=profiles,
        experiment_dirs=_discover_experiment_dirs(request, profiles),
    )


def _discover_profiles(request: MigrationRequest, old_package: Path, target_package: Path) -> tuple[Path, ...]:
    """Deduplicated union of explicit, walked-up, and package-local profiles.

    The command performs no global scan, so a profile outside this set is not
    discoverable and the caller must name it with ``--profile``.
    """
    candidates: list[Path] = [Path(profile) for profile in request.profiles]
    walked = _walk_up_for_profile(request.start_dir)
    if walked is not None:
        candidates.append(walked)
    for package in (old_package, target_package):
        if package.is_dir():
            candidates.extend(sorted(package.rglob(PROFILE_FILENAME)))
    return _resolve_unique(candidates)


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


def _discover_experiment_dirs(request: MigrationRequest, profiles: tuple[Path, ...]) -> tuple[Path, ...]:
    """Explicit directories plus the default tree each affected profile reserves."""
    candidates: list[Path] = [Path(directory) for directory in request.experiment_dirs]
    for profile in profiles:
        root = profile.parent.joinpath(*EXPERIMENT_DEFAULT_ROOT)
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
    """List every unrewritten literal in the staged tree, by path and line."""
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
        shutil.copyfile(source.root / rel, target)


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


def _stage(sources: list[_Source], dest: Path, agent: str) -> Manifest:
    """Build and validate the target package in *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    _merge_sources(sources, dest)
    _rename_contract(dest, agent)
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
# Profiles
# ---------------------------------------------------------------------------


@dataclass
class _ProfilePlan:
    """One affected ``optimizer.yaml`` and the rewrite it needs, if any."""

    path: Path
    data: dict[str, Any]
    rewritten: dict[str, Any] | None = None
    conflict: str | None = None

    @property
    def needs_rewrite(self) -> bool:
        return self.rewritten is not None


def _plan_profile(path: Path, plan: MigrationPlan) -> _ProfilePlan:
    """Read one profile and decide whether it needs a key or path rewrite."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return _ProfilePlan(path=path, data={}, conflict=f"{path}: cannot be read as YAML ({exc})")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _ProfilePlan(path=path, data={}, conflict=f"{path}: the document root must be a YAML mapping")

    old_value = payload.get(LEGACY_PROFILE_KEY)
    new_value = payload.get(ETHOS_PROFILE_KEY)
    if old_value is None and new_value is None:
        return _ProfilePlan(path=path, data=payload)
    if old_value is not None and not isinstance(old_value, str):
        return _ProfilePlan(path=path, data=payload, conflict=f"{path}: {LEGACY_PROFILE_KEY!r} must be a string path")
    if new_value is not None and not isinstance(new_value, str):
        return _ProfilePlan(path=path, data=payload, conflict=f"{path}: {ETHOS_PROFILE_KEY!r} must be a string path")

    source_value = old_value if old_value is not None else new_value
    assert source_value is not None  # exactly one of the two branches above set it
    try:
        rewritten_value = _rewrite_profile_value(source_value, plan)
    except MigrationError as exc:
        return _ProfilePlan(path=path, data=payload, conflict=f"{path}: {exc}")

    # A half-converted profile carries both keys. They agree when the old value
    # rewrites to the new one, which is the state a resumed migration leaves
    # behind; anything else is a divergence a rename must not silently resolve.
    if old_value is not None and new_value is not None and new_value != rewritten_value:
        return _ProfilePlan(
            path=path,
            data=payload,
            conflict=(
                f"{path}: {LEGACY_PROFILE_KEY} is {old_value!r} but {ETHOS_PROFILE_KEY} is "
                f"{new_value!r}; the two disagree, so keep one and rerun"
            ),
        )

    rewritten = _replace_profile_key(payload, rewritten_value)
    if rewritten == payload:
        return _ProfilePlan(path=path, data=payload)
    return _ProfilePlan(path=path, data=payload, rewritten=rewritten)


def _rewrite_profile_value(value: str, plan: MigrationPlan) -> str:
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
            f"{LEGACY_PROFILE_KEY} is {value!r}, which no rewrite rule turns into a path ending in "
            f"{ETHOS_FILENAME}. Point it at the agent's contract file and rerun"
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


def _profile_is_converted(path: Path, plan: MigrationPlan) -> bool:
    profile = _plan_profile(path, plan)
    return profile.conflict is None and not profile.needs_rewrite


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
    """Conservatively name every experiment directory that may still be resumable.

    Candidate records are the durable evidence that a run owns state on disk. A
    completed run is historical and never blocks. This can reject a
    non-resumable run, but it cannot let a resumable one through.
    """
    blocking: list[str] = []
    for directory in plan.experiment_dirs:
        state = directory / EXPERIMENT_STATE_DIRNAME
        candidates = sorted((state / "candidates").glob("*.json"))
        if not candidates:
            continue
        try:
            record = json.loads((state / "run.json").read_text(encoding="utf-8"))
            status = str(record.get("status", "")) if isinstance(record, dict) else ""
        except (OSError, UnicodeError, ValueError):
            blocking.append(
                f"{directory} keeps {len(candidates)} candidate record(s) but its run.json is missing or unreadable"
            )
            continue
        if status in BLOCKING_RUN_STATUSES:
            blocking.append(f"{directory} holds a {status} run with {len(candidates)} candidate record(s)")
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
# Assessment: discover, read, stage, classify, gate
# ---------------------------------------------------------------------------


@dataclass
class _Assessment:
    """Everything the apply sequence needs, all of it already read and verified."""

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

    old_local = build_manifest(plan.old_package) if plan.old_package.is_dir() else None
    target_local = build_manifest(plan.target_package) if plan.target_package.is_dir() else None
    old_remote_read = _read_fileset(filesets, plan.workspace, plan.old_fileset, stack)
    target_remote_read = _read_fileset(filesets, plan.workspace, plan.target_fileset, stack)
    old_remote = old_remote_read[0] if old_remote_read is not None else None
    target_remote = target_remote_read[0] if target_remote_read is not None else None

    profiles = [_plan_profile(path, plan) for path in plan.profiles]
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
        f"Profiles still naming the pre-rename artifact: {len(pending_profiles)}",
    ]

    staged_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".ethos-migrate-staged-"))) / "package"
    staged: Manifest | None = None
    if legacy_present:
        sources: list[_Source] = []
        if old_local is not None:
            sources.append(_Source("the local package", plan.old_package, old_local))
        if old_remote_read is not None:
            sources.append(_Source("the Fileset", old_remote_read[1], old_remote_read[0]))
        staged = _stage(sources, staged_dir, plan.agent)

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
                    "Conflict: the target is partial or divergent, and no legacy source or journal "
                    "explains it. Reconcile it by hand, then rerun; nothing was changed.",
                ],
                None,
            )
        if not pending_profiles:
            return Outcome.ALREADY_MIGRATED, [*lines, "Already migrated. Nothing to do."], None
        # Stage from the verified target so resuming profile conversion runs
        # through the same apply sequence a full migration does.
        shutil.copytree(plan.target_package, staged_dir)
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


def _target_is_complete(plan: MigrationPlan, target_local: Manifest | None, target_remote: Manifest | None) -> bool:
    """True when both target copies exist, match, and carry a parseable contract."""
    if target_local is None or target_remote is None or target_local != target_remote:
        return False
    try:
        _validate_contract(plan.target_package)
    except MigrationError:
        return False
    return True


def _location_lines(plan: MigrationPlan) -> list[str]:
    """Every location the command reads or writes, for the dry-run report."""
    lines = [
        f"Agent: {plan.agent}   Workspace: {plan.workspace}",
        f"Local package: {plan.old_package} -> {plan.target_package}",
        f"Fileset: {plan.old_fileset} -> {plan.target_fileset}",
        f"Journal: {journal_dir(plan.workspace, plan.agent)}",
        f"Affected profiles ({len(plan.profiles)}):",
        *(f"  {path}" for path in plan.profiles),
        f"Known experiment directories ({len(plan.experiment_dirs)}):",
        *(f"  {path}" for path in plan.experiment_dirs),
        "Custom profiles and experiment directories outside this set cannot be discovered, because "
        "the command performs no global scan. Pass each one with --profile or --experiment-dir.",
    ]
    return lines


# ---------------------------------------------------------------------------
# Locking and journal
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _exclusive_lock(directory: Path, plan: MigrationPlan) -> Iterator[None]:
    """Hold a non-blocking exclusive lock for the whole apply.

    The kernel releases the lock when the process exits, cleanly or not, so no
    stale lock record ever needs cleaning.
    """
    descriptor = os.open(directory / "lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MigrationError(
                f"another ethos migrate is already running for agent {plan.agent!r} in workspace "
                f"{plan.workspace!r}; nothing was read or written"
            ) from exc
        yield
    finally:
        os.close(descriptor)


def _write_journal(directory: Path, payload: dict[str, Any]) -> None:
    """Replace the journal atomically, so a crash never leaves a half-written record."""
    temporary = directory / "journal.json.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, directory / "journal.json")


def _discard_transaction_state(directory: Path) -> None:
    """Remove the journal and every backup. The lock file stays; the kernel owns it."""
    with contextlib.suppress(OSError):
        (directory / "journal.json").unlink()
    shutil.rmtree(directory / "backup", ignore_errors=True)


# ---------------------------------------------------------------------------
# Apply
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


def _apply(
    assessment: _Assessment,
    *,
    directory: Path,
    filesets: FilesetStore,
    lines: list[str],
    on_step: Callable[[str], None] | None,
) -> MigrationReport:
    """Run the compensating transaction.

    Every step before ``final-verify`` leaves the old local package, the old
    Fileset, and the old profile keys authoritative, so a failure anywhere can
    be undone from the journal and the backups.
    """
    plan = assessment.plan
    backups = directory / "backup"
    journal: dict[str, Any] = {
        "workspace": plan.workspace,
        "agent": plan.agent,
        "old_package": str(plan.old_package),
        "target_package": str(plan.target_package),
        "old_fileset": plan.old_fileset,
        "target_fileset": plan.target_fileset,
        "staged": _manifest_to_json(assessment.staged),
        "created_target_fileset": assessment.target_remote is None,
        "created_target_package": assessment.target_local is None,
        "had_old_package": assessment.old_local is not None,
        "had_old_fileset": assessment.old_remote is not None,
        "profile_backups": {},
        "steps": [],
        "failed_step": None,
    }
    _write_journal(directory, journal)

    def begin(name: str) -> None:
        if on_step is not None:
            on_step(name)

    def finish(name: str) -> None:
        journal["steps"].append(name)
        _write_journal(directory, journal)

    try:
        begin("backups")
        _build_backups(assessment, backups, filesets, journal)
        finish("backups")

        begin("upload-target-fileset")
        if assessment.target_remote is None:
            filesets.upload(workspace=plan.workspace, name=plan.target_fileset, source=assessment.staged_dir)
        finish("upload-target-fileset")

        begin("verify-target-fileset")
        _verify_remote(filesets, plan.workspace, plan.target_fileset, assessment.staged)
        finish("verify-target-fileset")

        begin("write-target-package")
        if assessment.target_local is None:
            _write_package(assessment.staged_dir, plan.target_package)
        finish("write-target-package")

        begin("rewrite-profiles")
        _rewrite_profiles(assessment, plan)
        finish("rewrite-profiles")

        begin("delete-old-fileset")
        if assessment.old_remote is not None:
            filesets.delete(workspace=plan.workspace, name=plan.old_fileset)
        finish("delete-old-fileset")

        begin("delete-old-package")
        if assessment.old_local is not None:
            shutil.rmtree(plan.old_package)
        finish("delete-old-package")

        begin("final-verify")
        _verify_final(assessment, filesets)
        finish("final-verify")
    except Exception as exc:
        failed = _failed_step(journal)
        journal["failed_step"] = failed
        _write_journal(directory, journal)
        try:
            _compensate(assessment, journal, filesets, backups)
        except Exception as compensation_error:
            raise RecoveryRequired(
                f"ethos migrate failed at step {failed!r} and could not undo its own work "
                f"({compensation_error}); status is recovery-required. The journal and backups "
                f"under {directory} are kept, and the next run recovers before any new work"
            ) from compensation_error
        _discard_transaction_state(directory)
        raise MigrationError(
            f"ethos migrate failed at step {failed!r} ({exc}); the old local package, the old "
            "Fileset, and the old profile keys were restored and remain authoritative"
        ) from exc

    _discard_transaction_state(directory)
    return MigrationReport(outcome=Outcome.MIGRATED, lines=[*lines, "Migrated."])


def _failed_step(journal: dict[str, Any]) -> str:
    completed = set(journal["steps"])
    return next((name for name in _STEPS if name not in completed), _STEPS[-1])


def _build_backups(assessment: _Assessment, backups: Path, filesets: FilesetStore, journal: dict[str, Any]) -> None:
    """Copy every legacy source and affected profile, then verify each by checksum."""
    plan = assessment.plan
    backups.mkdir(parents=True, exist_ok=True)

    if assessment.old_local is not None:
        destination = backups / "legacy-local"
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(plan.old_package, destination)
        if build_manifest(destination) != assessment.old_local:
            raise MigrationError(f"the backup of {plan.old_package} does not match its source")

    if assessment.old_remote is not None:
        destination = backups / "legacy-remote"
        shutil.rmtree(destination, ignore_errors=True)
        filesets.download(workspace=plan.workspace, name=plan.old_fileset, dest=destination)
        if build_manifest(destination) != assessment.old_remote:
            raise MigrationError(f"the backup of Fileset {plan.old_fileset!r} does not match its source")

    profile_backups = backups / "profiles"
    profile_backups.mkdir(parents=True, exist_ok=True)
    for index, profile in enumerate(assessment.profiles):
        destination = profile_backups / f"{index:03d}-{profile.path.name}"
        shutil.copyfile(profile.path, destination)
        if _fingerprint(destination) != _fingerprint(profile.path):
            raise MigrationError(f"the backup of {profile.path} does not match its source")
        journal["profile_backups"][str(profile.path)] = str(destination)


def _rewrite_profiles(assessment: _Assessment, plan: MigrationPlan) -> None:
    for profile in assessment.profiles:
        if profile.rewritten is not None:
            _write_profile(profile.path, profile.rewritten)
    for profile in assessment.profiles:
        if profile.rewritten is not None and not _profile_is_converted(profile.path, plan):
            raise MigrationError(f"{profile.path} still names the pre-rename artifact after the rewrite")


def _write_package(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(staged, target)


def _verify_remote(filesets: FilesetStore, workspace: str, name: str, expected: Manifest) -> None:
    """Download the Fileset and compare manifests, because the list API has no checksum."""
    with tempfile.TemporaryDirectory(prefix=f".ethos-migrate-verify-{name}-") as tmp:
        dest = Path(tmp)
        filesets.download(workspace=workspace, name=name, dest=dest)
        actual = build_manifest(dest)
    if actual != expected:
        raise MigrationError(f"Fileset {workspace}/{name} does not match the expected manifest")


def _verify_final(assessment: _Assessment, filesets: FilesetStore) -> None:
    """Confirm the complete final target and the converted profiles before committing."""
    plan = assessment.plan
    if build_manifest(plan.target_package) != assessment.staged:
        raise MigrationError(f"{plan.target_package} does not match the staged package")
    _validate_contract(plan.target_package)
    _verify_remote(filesets, plan.workspace, plan.target_fileset, assessment.staged)
    for profile in assessment.profiles:
        if not _profile_is_converted(profile.path, plan):
            raise MigrationError(f"{profile.path} still names the pre-rename artifact")
    if plan.old_package.exists():
        raise MigrationError(f"{plan.old_package} still exists")
    if filesets.exists(workspace=plan.workspace, name=plan.old_fileset):
        raise MigrationError(f"Fileset {plan.workspace}/{plan.old_fileset} still exists")


# ---------------------------------------------------------------------------
# Compensation and recovery
# ---------------------------------------------------------------------------


def _undo(journal: dict[str, Any], plan: MigrationPlan, filesets: FilesetStore, backups: Path) -> None:
    """Undo this transaction's writes from the journal and the backups.

    Each action is conditional on current state, so re-running it after a
    partial compensation is safe. Pre-existing target state the transaction did
    not create is left untouched.
    """
    for raw_path, raw_backup in journal["profile_backups"].items():
        backup = Path(raw_backup)
        if backup.is_file():
            shutil.copyfile(backup, Path(raw_path))
    if journal["created_target_package"] and plan.target_package.exists():
        shutil.rmtree(plan.target_package)
    if journal["created_target_fileset"] and filesets.exists(workspace=plan.workspace, name=plan.target_fileset):
        filesets.delete(workspace=plan.workspace, name=plan.target_fileset)
    if journal["had_old_package"] and not plan.old_package.exists():
        shutil.copytree(backups / "legacy-local", plan.old_package)
    if journal["had_old_fileset"] and not filesets.exists(workspace=plan.workspace, name=plan.old_fileset):
        filesets.upload(workspace=plan.workspace, name=plan.old_fileset, source=backups / "legacy-remote")


def _compensate(assessment: _Assessment, journal: dict[str, Any], filesets: FilesetStore, backups: Path) -> None:
    """Undo the failed transaction, then verify the old state is authoritative again."""
    plan = assessment.plan
    _undo(journal, plan, filesets, backups)

    if assessment.old_local is not None and build_manifest(plan.old_package) != assessment.old_local:
        raise MigrationError(f"{plan.old_package} was not restored to its original contents")
    if assessment.old_remote is not None:
        _verify_remote(filesets, plan.workspace, plan.old_fileset, assessment.old_remote)
    for profile in assessment.profiles:
        if profile.rewritten is None:
            continue
        if _plan_profile(profile.path, plan).data != profile.data:
            raise MigrationError(f"{profile.path} was not restored to its original contents")


def _recover(directory: Path, plan: MigrationPlan, filesets: FilesetStore) -> MigrationReport:
    """Finish or undo the transaction the journal describes, before any new work."""
    journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
    backups = directory / "backup"
    staged = _manifest_from_json(journal["staged"])

    legacy_gone = not plan.old_package.is_dir() and not filesets.exists(workspace=plan.workspace, name=plan.old_fileset)
    if legacy_gone and _target_is_committed(plan, filesets, staged):
        _discard_transaction_state(directory)
        return MigrationReport(
            outcome=Outcome.RECOVERED,
            lines=[
                f"Recovered: the interrupted migration of {plan.agent!r} had already committed, so "
                "only cleanup remained. The target is authoritative.",
            ],
        )

    try:
        _undo(journal, plan, filesets, backups)
        if journal["had_old_package"]:
            if build_manifest(plan.old_package) != build_manifest(backups / "legacy-local"):
                raise MigrationError(f"{plan.old_package} was not restored to its backed-up contents")
        if journal["had_old_fileset"]:
            _verify_remote(filesets, plan.workspace, plan.old_fileset, build_manifest(backups / "legacy-remote"))
    except Exception as exc:
        raise RecoveryRequired(
            f"recovery of the interrupted migration of {plan.agent!r} failed ({exc}); status is "
            f"recovery-required. The journal and backups under {directory} are kept"
        ) from exc

    _discard_transaction_state(directory)
    return MigrationReport(
        outcome=Outcome.RECOVERED,
        lines=[
            f"Recovered: undid the interrupted migration of {plan.agent!r}, which failed at step "
            f"{journal.get('failed_step')!r}. The pre-rename state is authoritative again; rerun to migrate.",
        ],
    )


def _target_is_committed(plan: MigrationPlan, filesets: FilesetStore, staged: Manifest) -> bool:
    """True when the interrupted transaction had already reached its commit point."""
    if not plan.target_package.is_dir() or build_manifest(plan.target_package) != staged:
        return False
    try:
        _validate_contract(plan.target_package)
        _verify_remote(filesets, plan.workspace, plan.target_fileset, staged)
    except MigrationError:
        return False
    return all(_profile_is_converted(path, plan) for path in plan.profiles)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_migration(
    request: MigrationRequest,
    *,
    filesets: FilesetStore,
    jobs: JobStore,
    on_step: Callable[[str], None] | None = None,
) -> MigrationReport:
    """Migrate one agent's Ethos artifacts, or report why it cannot.

    Args:
        request: The agent, workspace, roots, and caller-named paths.
        filesets: Fileset port.
        jobs: Platform Jobs port.
        on_step: Called with each mutating step name just before that step runs.
            Raise from it to abort mid-transaction, which is how compensation is
            exercised.

    Returns:
        A report whose ``outcome`` names the state-table row that applied.

    Raises:
        MigrationError: A controlled failure. The old state was restored and
            remains authoritative.
        RecoveryRequired: Compensation failed. The journal and backups are kept,
            and the next run recovers before any new work.
    """
    plan = _build_plan(request)

    if request.dry_run:
        # Read-only: no journal, lock file, package, Fileset, or profile backup.
        with contextlib.ExitStack() as stack:
            outcome, lines, _ = _classify(plan, filesets, jobs, stack)
        if outcome is Outcome.PENDING:
            lines = [*lines, "Migration is required. Rerun without --dry-run to apply it."]
        return MigrationReport(outcome=outcome, lines=["Dry run — nothing was written.", *lines])

    directory = journal_dir(request.workspace, request.agent)
    directory.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(directory, plan):
        if (directory / "journal.json").is_file():
            return _recover(directory, plan, filesets)
        with contextlib.ExitStack() as stack:
            outcome, lines, assessment = _classify(plan, filesets, jobs, stack)
            if assessment is None:
                return MigrationReport(outcome=outcome, lines=lines)
            return _apply(assessment, directory=directory, filesets=filesets, lines=lines, on_step=on_step)


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
