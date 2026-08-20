# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Migrate an agent package from the legacy contract name to Ethos."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from nemo_agents_plugin.entities import ETHOS_FILENAME, ETHOS_LOCAL_ROOT, ethos_fileset_name
from nemo_agents_plugin.ethos_parse import EthosParseError, parse_ethos

LEGACY_CONTRACT_FILENAME = "AGENT-SPEC.md"
LEGACY_PACKAGE_SUFFIX = "-spec"
LEGACY_WRITER_SKILL = "nemo-spec"
ETHOS_WRITER_SKILL = "nemo-ethos"
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION = re.compile(r"^## +", re.MULTILINE)


class MigrationError(RuntimeError):
    """Raised when migration cannot preserve matching target bytes."""


@dataclass(frozen=True)
class MigrationRequest:
    """Identifies one platform-managed agent package and workspace."""

    agent: str
    workspace: str = "default"
    agents_root: Path = Path(ETHOS_LOCAL_ROOT)
    dry_run: bool = False
    cleanup: bool = False


@dataclass
class MigrationReport:
    """Contains the command outcome and messages."""

    outcome: str
    lines: list[str] = field(default_factory=list)


def validate_agent_name(agent: str) -> None:
    """Reject a name that cannot safely name one child directory."""
    if not agent or agent in {".", ".."} or "\0" in agent:
        raise MigrationError("--name must be one non-empty path component")
    if "/" in agent or "\\" in agent or Path(agent).is_absolute() or Path(agent).name != agent:
        raise MigrationError("--name must be one path component")


def registration_migration_warning(agent: str, workspace: str, agent_config: Path) -> tuple[str, ...]:
    """Return migration guidance for a platform-managed legacy package."""
    try:
        validate_agent_name(agent)
    except MigrationError:
        return ()
    package = Path(ETHOS_LOCAL_ROOT) / f"{agent}{LEGACY_PACKAGE_SUFFIX}"
    if agent_config.parent.resolve() != package.resolve():
        return ()
    if not (package / LEGACY_CONTRACT_FILENAME).is_file():
        return ()
    command = shlex.join(
        [
            "nemo",
            "agents",
            "ethos",
            "migrate",
            "--name",
            agent,
            "--workspace",
            workspace,
        ]
    )
    return (
        f"Warning: This package uses the legacy {LEGACY_CONTRACT_FILENAME} format.",
        f"Upgrade to {ETHOS_FILENAME} using:",
        command,
    )


def _manifest(root: Path) -> dict[str, tuple[int, str]]:
    if root.is_symlink():
        raise MigrationError(f"{root} is a symlink")
    if not root.is_dir():
        raise MigrationError(f"{root} is not a directory")
    manifest: dict[str, tuple[int, str]] = {}
    for parent, directories, files in os.walk(root, followlinks=False):
        here = Path(parent)
        for name in directories + files:
            if (here / name).is_symlink():
                raise MigrationError(f"{root} contains symlink {(here / name).relative_to(root)}")
        for name in files:
            path = here / name
            if not path.is_file():
                raise MigrationError(f"{path} is not a regular file")
            payload = path.read_bytes()
            manifest[path.relative_to(root).as_posix()] = (len(payload), hashlib.sha256(payload).hexdigest())
    return dict(sorted(manifest.items()))


def _reject_package_symlink(path: Path) -> None:
    if path.is_symlink():
        raise MigrationError(f"{path} is a symlink")


def _fileset_exists(sdk: Any, workspace: str, name: str) -> bool:
    from nemo_platform import NotFoundError as PlatformNotFoundError
    from nemo_platform_plugin.client.errors import NotFoundError as PluginNotFoundError

    try:
        sdk.files.filesets.retrieve(name, workspace=workspace)
    except (PlatformNotFoundError, PluginNotFoundError):
        return False
    return True


def _download(sdk: Any, workspace: str, name: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    sdk.files.download(local_path=str(destination), fileset=name, workspace=workspace)


def _rewrite_contract(package: Path, agent: str) -> None:
    legacy = package / LEGACY_CONTRACT_FILENAME
    target = package / ETHOS_FILENAME
    if target.exists() and legacy.exists():
        raise MigrationError("source contains both contract filenames")
    if legacy.exists():
        text = legacy.read_text()
        front = _FRONT_MATTER.match(text)
        if front is None:
            raise MigrationError("legacy contract lacks YAML front matter")
        body = text[front.end() :]
        first_section = _SECTION.search(body)
        end = first_section.start() if first_section else len(body)
        identity = body[:end].replace("# Agent Spec:", "# Ethos:")
        identity = identity.replace(LEGACY_CONTRACT_FILENAME, ETHOS_FILENAME)
        identity = identity.replace(LEGACY_WRITER_SKILL, ETHOS_WRITER_SKILL)
        identity = identity.replace(f"{agent}{LEGACY_PACKAGE_SUFFIX}", ethos_fileset_name(agent))
        target.write_text(text[: front.end()] + identity + body[end:])
        legacy.unlink()
    if not target.is_file():
        raise MigrationError(f"source has no {LEGACY_CONTRACT_FILENAME}")


def _validate(package: Path) -> dict[str, tuple[int, str]]:
    manifest = _manifest(package)
    try:
        parse_ethos((package / ETHOS_FILENAME).read_text())
    except (EthosParseError, OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MigrationError(f"{ETHOS_FILENAME} is invalid: {exc}") from exc
    return manifest


def _merge(sources: list[Path], staged: Path) -> None:
    seen: dict[str, tuple[Path, tuple[int, str]]] = {}
    for source in sources:
        for rel, fingerprint in _manifest(source).items():
            previous = seen.get(rel)
            if previous and previous[1] != fingerprint:
                raise MigrationError(f"legacy sources disagree at {rel}")
            seen[rel] = (source, fingerprint)
    for rel, (source, _) in seen.items():
        destination = staged / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, destination)


def _complete_local(staged: Path, target: Path, manifest: dict[str, tuple[int, str]], write: bool) -> None:
    _reject_package_symlink(target)
    if target.exists():
        actual = _manifest(target)
        if any(manifest.get(name) != fingerprint for name, fingerprint in actual.items()):
            raise MigrationError("local target differs from staged output")
    if not write:
        return
    target.mkdir(parents=True, exist_ok=True)
    for rel in manifest:
        destination = target / rel
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged / rel, destination)
    if _manifest(target) != manifest:
        raise MigrationError("local target is not a complete staged match")


def _complete_fileset(
    sdk: Any, workspace: str, name: str, staged: Path, manifest: dict[str, tuple[int, str]], write: bool
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory)
        exists = _fileset_exists(sdk, workspace, name)
        if exists:
            _download(sdk, workspace, name, target)
            actual = _manifest(target)
            if any(manifest.get(item) != fingerprint for item, fingerprint in actual.items()):
                raise MigrationError("Fileset target differs from staged output")
        if not write:
            return
        if exists and actual == manifest:
            return
        if not exists:
            sdk.files.filesets.create(name=name, workspace=workspace)
        sdk.files.upload(local_path=f"{staged}/", fileset=name, workspace=workspace, fileset_auto_create=False)
        shutil.rmtree(target)
        target.mkdir()
        _download(sdk, workspace, name, target)
        remote_manifest = _manifest(target)
        if remote_manifest != manifest:
            raise MigrationError("Fileset target is not a complete staged match")


def _targets_match(sdk: Any, workspace: str, local: Path, fileset: str) -> bool:
    _reject_package_symlink(local)
    if not local.is_dir() or not _fileset_exists(sdk, workspace, fileset):
        return False
    local_manifest = _validate(local)
    with tempfile.TemporaryDirectory() as directory:
        remote = Path(directory)
        _download(sdk, workspace, fileset, remote)
        remote_manifest = _validate(remote)
        return remote_manifest == local_manifest


def run_migration(request: MigrationRequest, *, sdk: Any) -> MigrationReport:
    """Run the additive migration or explicit cleanup for one agent."""
    validate_agent_name(request.agent)
    root = request.agents_root.resolve()
    old = root / f"{request.agent}{LEGACY_PACKAGE_SUFFIX}"
    target = root / ethos_fileset_name(request.agent)
    old_fileset = f"{request.agent}{LEGACY_PACKAGE_SUFFIX}"
    target_fileset = ethos_fileset_name(request.agent)
    _reject_package_symlink(old)
    _reject_package_symlink(target)

    if request.cleanup:
        if not _targets_match(sdk, request.workspace, target, target_fileset):
            raise MigrationError("cleanup requires complete matching targets")
        if request.dry_run:
            return MigrationReport("pending", ["Dry run: cleanup would remove legacy artifacts."])
        if old.exists():
            if old.is_symlink():
                raise MigrationError(f"{old} is a symlink")
            shutil.rmtree(old)
        if _fileset_exists(sdk, request.workspace, old_fileset):
            sdk.files.filesets.delete(old_fileset, workspace=request.workspace)
        return MigrationReport("cleaned", ["Removed legacy local package and Fileset."])

    sources: list[Path] = []
    if old.exists():
        if old.is_symlink():
            raise MigrationError(f"{old} is a symlink")
        sources.append(old)
    with tempfile.TemporaryDirectory() as directory:
        remote = Path(directory) / "legacy"
        if _fileset_exists(sdk, request.workspace, old_fileset):
            _download(sdk, request.workspace, old_fileset, remote)
            sources.append(remote)
        if not sources:
            if _targets_match(sdk, request.workspace, target, target_fileset):
                return MigrationReport("already-migrated", ["Targets already match."])
            raise MigrationError("no legacy source is available")
        staged = Path(directory) / "staged"
        staged.mkdir()
        _merge(sources, staged)
        _rewrite_contract(staged, request.agent)
        manifest = _validate(staged)
        _complete_local(staged, target, manifest, write=False)
        _complete_fileset(sdk, request.workspace, target_fileset, staged, manifest, write=False)
        if not request.dry_run:
            _complete_local(staged, target, manifest, write=True)
            _complete_fileset(sdk, request.workspace, target_fileset, staged, manifest, write=True)
    if request.dry_run:
        return MigrationReport("pending", ["Dry run: additive migration is valid."])
    return MigrationReport("migrated", ["Created or completed matching Ethos targets."])
