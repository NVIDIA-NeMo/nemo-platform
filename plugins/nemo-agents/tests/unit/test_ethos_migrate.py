# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``nemo agents ethos migrate``.

This file and ``nemo_agents_plugin.ethos_migrate`` are the only places in the
plugin allowed to name the pre-rename artifact, because migration owns every
old-name lookup.

Filesets and Jobs are covered by small in-memory fakes that hold real bytes, and
failures are injected at the module's real operation boundaries — its filesystem,
profile-write, and journal-write functions — rather than through a hook in the
transaction. Ordering is therefore observed through those boundaries instead of
asserted against a call log.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from nemo_agents_plugin import ethos_migrate
from nemo_agents_plugin.cli import AgentsCLI
from nemo_agents_plugin.ethos_migrate import (
    JobRecord,
    MigrationError,
    MigrationRequest,
    Outcome,
    RecoveryRequired,
    SdkFilesetStore,
    SdkJobStore,
    build_manifest,
    journal_dir,
    run_migration,
    validate_agent_name,
)
from typer.testing import CliRunner

AGENT = "acme-bot"
WORKSPACE = "default"

LEGACY_CONTRACT_FILENAME = "AGENT-SPEC.md"
LEGACY_PACKAGE = f"{AGENT}-spec"
TARGET_PACKAGE = f"{AGENT}-ethos"
LEGACY_PROFILE_KEY = "agent_spec"

SECTION_TITLES = (
    "Role",
    "Purpose",
    "Scope",
    "Tools",
    "Model",
    "Framework",
    "Harness",
    "Behavior",
    "Success Criteria",
    "Evaluation Setup",
    "Change Scope",
    "Signals",
    "Open Questions",
)


def section_body(title: str) -> str:
    """Distinctive body text so a lost or reordered section is visible."""
    slug = title.lower().replace(" ", "-")
    return f"body-for-{slug}\n\n- detail one for {title}\n- detail two for {title}"


def legacy_contract(name: str = AGENT) -> str:
    """A valid pre-rename contract file, banner and H1 included."""
    lines = [
        "---",
        f"name: {name}",
        "created_timestamp: 2026-08-19T12:00:00Z",
        "author: tester",
        "---",
        "",
        f"# Agent Spec: {name}",
        "",
        f"> This file is the agent's {LEGACY_CONTRACT_FILENAME} — the durable contract",
        "> that describes intended behavior. `nemo-spec` writes it.",
        "",
    ]
    for title in SECTION_TITLES:
        lines += [f"## {title}", "", section_body(title), ""]
    return "\n".join(lines)


def target_contract(name: str = AGENT) -> str:
    """The staged output the migrator must produce from :func:`legacy_contract`."""
    lines = [
        "---",
        f"name: {name}",
        "created_timestamp: 2026-08-19T12:00:00Z",
        "author: tester",
        "---",
        "",
        f"# Ethos: {name}",
        "",
        "> This file is the agent's ETHOS.md — the durable contract",
        "> that describes intended behavior. `nemo-ethos` writes it.",
        "",
    ]
    for title in SECTION_TITLES:
        lines += [f"## {title}", "", section_body(title), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fake platform adapters
# ---------------------------------------------------------------------------


@dataclass
class FakeFilesets:
    """In-memory Filesets holding real bytes keyed by relative POSIX path.

    ``create`` is conditional the way the platform's is: it returns False when the
    Fileset already exists. ``upload`` refuses a Fileset that does not exist,
    mirroring ``fileset_auto_create=False``, so nothing can come into being
    without a decided ownership.
    """

    trees: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    fail_create: set[str] = field(default_factory=set)
    fail_upload: set[str] = field(default_factory=set)
    fail_delete: set[str] = field(default_factory=set)
    drop_on_upload: dict[str, set[str]] = field(default_factory=dict)
    # Another writer wins the create race: create installs their tree and reports
    # that this caller did not create the Fileset.
    steal_on_create: dict[str, dict[str, bytes]] = field(default_factory=dict)
    creates: list[str] = field(default_factory=list)
    uploads: list[str] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)
    observer: Callable[[str, str], None] | None = None

    def seed(self, name: str, tree: dict[str, bytes], *, workspace: str = WORKSPACE) -> None:
        self.trees[(workspace, name)] = dict(tree)

    def _observe(self, operation: str, name: str) -> None:
        if self.observer is not None:
            self.observer(operation, name)

    def exists(self, *, workspace: str, name: str) -> bool:
        return (workspace, name) in self.trees

    def create(self, *, workspace: str, name: str) -> bool:
        self._observe("create", name)
        self.creates.append(name)
        if name in self.fail_create:
            raise OSError(f"injected create failure for {name}")
        stolen = self.steal_on_create.get(name)
        if stolen is not None:
            self.trees.setdefault((workspace, name), dict(stolen))
            return False
        if (workspace, name) in self.trees:
            return False
        self.trees[(workspace, name)] = {}
        return True

    def download(self, *, workspace: str, name: str, dest: Path) -> None:
        tree = self.trees.get((workspace, name))
        if tree is None:
            raise KeyError(f"no such fileset: {workspace}/{name}")
        for rel, payload in tree.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

    def upload(self, *, workspace: str, name: str, source: Path) -> None:
        self._observe("upload", name)
        self.uploads.append(name)
        if name in self.fail_upload:
            raise OSError(f"injected upload failure for {name}")
        if (workspace, name) not in self.trees:
            raise OSError(f"fileset {workspace}/{name} does not exist and auto-create is disabled")
        tree = self.trees[(workspace, name)]
        dropped = self.drop_on_upload.get(name, set())
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source).as_posix()
            # A silently lossy upload: the platform reports success but the
            # fileset is short a file, which only a download can reveal.
            if path.is_file() and rel not in dropped:
                tree[rel] = path.read_bytes()

    def delete(self, *, workspace: str, name: str) -> None:
        self._observe("delete", name)
        self.deletes.append(name)
        if name in self.fail_delete:
            raise OSError(f"injected delete failure for {name}")
        self.trees.pop((workspace, name), None)


@dataclass
class FakeJobs:
    """In-memory Platform Jobs listing."""

    records: list[JobRecord] = field(default_factory=list)

    def list_jobs(self, *, workspace: str) -> list[JobRecord]:
        return [record for record in self.records if record.workspace == workspace]


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def write_tree(root: Path, files: dict[str, bytes | str]) -> None:
    for rel, payload in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_bytes(payload)


def legacy_package_files() -> dict[str, bytes | str]:
    """A complete pre-rename package: contract file plus non-contract artifacts."""
    return {
        LEGACY_CONTRACT_FILENAME: legacy_contract(),
        "agent.yaml": "config_format: nemo-agents-spec-v1\nname: acme-bot\n",
        "skills/triage/SKILL.md": "# Triage skill\n\nagent-specific guidance.\n",
        "data/logo.bin": b"\x00\x01\x02\xff\xfe",
    }


def make_local_package(agents_root: Path, *, name: str = LEGACY_PACKAGE) -> Path:
    package = agents_root / name
    write_tree(package, legacy_package_files())
    return package


def as_fileset_tree(files: dict[str, bytes | str]) -> dict[str, bytes]:
    return {rel: (v.encode("utf-8") if isinstance(v, str) else v) for rel, v in files.items()}


def write_profile(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def request_for(
    tmp_path: Path,
    *,
    profiles: tuple[Path, ...] = (),
    experiment_dirs: tuple[Path, ...] = (),
    dry_run: bool = False,
    agents_root: Path | None = None,
) -> MigrationRequest:
    return MigrationRequest(
        agent=AGENT,
        workspace=WORKSPACE,
        agents_root=agents_root if agents_root is not None else tmp_path / "agents",
        profiles=profiles,
        experiment_dirs=experiment_dirs,
        dry_run=dry_run,
        start_dir=tmp_path / "cwd-with-no-profile",
    )


def migrate(request: MigrationRequest, filesets: FakeFilesets, jobs: FakeJobs | None = None):
    return run_migration(request, filesets=filesets, jobs=jobs or FakeJobs())


@pytest.fixture(autouse=True)
def _guard_journal_isolation(tmp_path: Path) -> None:
    """Refuse to run if the journal would land in the developer's real data dir.

    ``conftest`` pins ``NMP_DATA_DIR`` through ``monkeypatch.setenv``, and the
    ``monkeypatch`` fixture is shared with each test. A test that called
    ``monkeypatch.undo()`` would therefore silently un-isolate itself and write
    to ``~/.local/share/nemo``. Scoped ``MonkeyPatch.context()`` blocks are used
    instead of ``undo()``; this fixture fails loudly if that ever slips.
    """
    directory = journal_dir(WORKSPACE, AGENT)
    assert Path.home() not in directory.parents, f"journal would land in the real home dir: {directory}"


# ---------------------------------------------------------------------------
# Failure injection at real operation boundaries
# ---------------------------------------------------------------------------


def fail_copy_tree_into(monkeypatch: pytest.MonkeyPatch, destination: Path) -> None:
    real = ethos_migrate._copy_tree

    def guarded(source: Path, target: Path) -> None:
        if target == destination:
            raise OSError(f"injected copy failure for {target}")
        real(source, target)

    monkeypatch.setattr(ethos_migrate, "_copy_tree", guarded)


def fail_remove_tree(monkeypatch: pytest.MonkeyPatch, victim: Path) -> None:
    real = ethos_migrate._remove_tree

    def guarded(path: Path) -> None:
        if path == victim:
            raise OSError(f"injected remove failure for {path}")
        real(path)

    monkeypatch.setattr(ethos_migrate, "_remove_tree", guarded)


def fail_profile_write(monkeypatch: pytest.MonkeyPatch, victim: Path) -> None:
    real = ethos_migrate._write_profile

    def guarded(path: Path, payload: dict[str, Any]) -> None:
        if path == victim:
            raise OSError(f"injected profile write failure for {path}")
        real(path, payload)

    monkeypatch.setattr(ethos_migrate, "_write_profile", guarded)


def fail_journal_writes_from(monkeypatch: pytest.MonkeyPatch, first_failing_call: int) -> None:
    """Fail every journal write from the *first_failing_call*-th onwards (1-based)."""
    real = ethos_migrate._write_journal
    calls = {"n": 0}

    def guarded(directory: Path, payload: dict[str, Any]) -> None:
        calls["n"] += 1
        if calls["n"] >= first_failing_call:
            raise OSError(f"injected journal write failure on call {calls['n']}")
        real(directory, payload)

    monkeypatch.setattr(ethos_migrate, "_write_journal", guarded)


def fail_verify_final(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    def guarded(record: Any, filesets: Any) -> None:
        raise error

    monkeypatch.setattr(ethos_migrate, "_verify_final", guarded)


MUTATING_STEPS = (
    "backups",
    "upload-target-fileset",
    "verify-target-fileset",
    "write-target-package",
    "rewrite-profiles",
    "delete-old-fileset",
    "delete-old-package",
    "final-verify",
)


def inject_step_failure(
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    *,
    filesets: FakeFilesets,
    agents_root: Path,
    profile: Path,
) -> None:
    """Break the real operation each apply step depends on."""
    backups = journal_dir(WORKSPACE, AGENT) / "backup"
    if step == "backups":
        fail_copy_tree_into(monkeypatch, backups / "legacy-local")
    elif step == "upload-target-fileset":
        filesets.fail_upload.add(TARGET_PACKAGE)
    elif step == "verify-target-fileset":
        filesets.drop_on_upload[TARGET_PACKAGE] = {"data/logo.bin"}
    elif step == "write-target-package":
        fail_copy_tree_into(monkeypatch, agents_root / TARGET_PACKAGE)
    elif step == "rewrite-profiles":
        fail_profile_write(monkeypatch, profile)
    elif step == "delete-old-fileset":
        filesets.fail_delete.add(LEGACY_PACKAGE)
    elif step == "delete-old-package":
        fail_remove_tree(monkeypatch, agents_root / LEGACY_PACKAGE)
    elif step == "final-verify":
        fail_verify_final(monkeypatch, RuntimeError("injected final-verify failure"))
    else:  # pragma: no cover - guards a typo in the parametrization
        raise AssertionError(f"unknown step {step!r}")


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_ethos_migrate_is_registered_with_its_documented_options() -> None:
    result = CliRunner().invoke(AgentsCLI().get_cli(), ["ethos", "migrate", "--help"])

    assert result.exit_code == 0
    for option in (
        "--name",
        "--workspace",
        "--agents-root",
        "--profile",
        "--experiment-dir",
        "--dry-run",
        "--base-url",
    ):
        assert option in result.stdout


def test_ethos_group_is_listed_on_the_agents_cli() -> None:
    result = CliRunner().invoke(AgentsCLI().get_cli(), ["--help"])

    assert result.exit_code == 0
    assert "ethos" in result.stdout


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "/absolute", "nested/name", "nested\\name", "with\0nul", "trailing/", "./relative"],
)
def test_unsafe_agent_names_are_rejected(name: str) -> None:
    with pytest.raises(MigrationError):
        validate_agent_name(name)


@pytest.mark.parametrize("name", [AGENT, "a-b-c", "agent.v2", "Agent_1"])
def test_safe_agent_names_are_accepted(name: str) -> None:
    validate_agent_name(name)


@pytest.mark.parametrize("name", ["../escape", "/etc", "..", "a/b"])
def test_the_cli_rejects_an_unsafe_name_without_touching_the_filesystem(tmp_path: Path, name: str) -> None:
    outside = tmp_path / "outside"
    write_tree(outside, {"keep.txt": "untouched"})
    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    result = CliRunner().invoke(
        AgentsCLI().get_cli(),
        ["ethos", "migrate", "--name", name, "--agents-root", str(agents_root), "--dry-run"],
    )

    assert result.exit_code == 1
    assert "--name" in result.output
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "untouched"
    assert list(agents_root.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "a/b", "..", ".", ""])
def test_run_migration_rejects_an_unsafe_name_before_reading_anything(tmp_path: Path, name: str) -> None:
    """The core API validates too, so a library caller cannot skip the check."""
    outside = tmp_path / "outside"
    write_tree(outside, {"keep.txt": "untouched"})
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    request = MigrationRequest(agent=name, workspace=WORKSPACE, agents_root=agents_root, start_dir=tmp_path)

    with pytest.raises(MigrationError, match="--name"):
        run_migration(request, filesets=filesets, jobs=FakeJobs())

    assert (outside / "keep.txt").read_text(encoding="utf-8") == "untouched"
    assert list(agents_root.iterdir()) == []
    assert filesets.creates == []
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_an_escaping_name_cannot_reach_a_package_outside_the_agents_root(tmp_path: Path) -> None:
    """``../outside`` would resolve to a sibling of --agents-root, so it is refused."""
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    # Exactly where ``--name ../outside`` would land the legacy package.
    escape_target = tmp_path / "outside-spec"
    write_tree(escape_target, legacy_package_files())
    before = build_manifest(escape_target)
    filesets = FakeFilesets()

    with pytest.raises(MigrationError, match="--name"):
        run_migration(
            MigrationRequest(agent="../outside", workspace=WORKSPACE, agents_root=agents_root, start_dir=tmp_path),
            filesets=filesets,
            jobs=FakeJobs(),
        )

    assert build_manifest(escape_target) == before
    assert not (tmp_path / "outside-ethos").exists()
    assert filesets.creates == []
    assert filesets.deletes == []


def test_a_symlinked_legacy_package_root_is_refused_and_its_target_survives(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "real-package"
    write_tree(outside, legacy_package_files())
    before = build_manifest(outside)
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    (agents_root / LEGACY_PACKAGE).symlink_to(outside, target_is_directory=True)
    filesets = FakeFilesets()

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert "symlink" in "\n".join(report.lines)
    assert build_manifest(outside) == before
    assert (agents_root / LEGACY_PACKAGE).is_symlink()
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_a_broken_symlink_at_the_target_package_path_is_refused(tmp_path: Path) -> None:
    """A dangling link is not "absent": writing through it would leave the agents root."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    (agents_root / TARGET_PACKAGE).symlink_to(tmp_path / "does-not-exist")
    filesets = FakeFilesets()

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert "symlink" in "\n".join(report.lines)
    assert (agents_root / LEGACY_PACKAGE).is_dir()
    assert filesets.creates == []
    assert filesets.uploads == []


def test_a_symlinked_target_package_root_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "decoy"
    write_tree(outside, {"keep.txt": "untouched"})
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    (agents_root / TARGET_PACKAGE).symlink_to(outside, target_is_directory=True)

    report = migrate(request_for(tmp_path), FakeFilesets())

    assert report.outcome is Outcome.CONFLICT
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "untouched"
    assert (agents_root / LEGACY_PACKAGE).is_dir()


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


def test_build_manifest_keys_relative_posix_paths_with_size_and_digest(tmp_path: Path) -> None:
    write_tree(tmp_path, {"a.md": "hello", "nested/b.bin": b"\x00\x01"})

    manifest = build_manifest(tmp_path)

    assert set(manifest) == {"a.md", "nested/b.bin"}
    assert manifest["a.md"].size == 5
    assert manifest["nested/b.bin"].size == 2
    assert len(manifest["a.md"].sha256) == 64
    assert manifest["a.md"].sha256 != manifest["nested/b.bin"].sha256


def test_build_manifest_rejects_symlinks(tmp_path: Path) -> None:
    write_tree(tmp_path, {"real.md": "x"})
    (tmp_path / "link.md").symlink_to(tmp_path / "real.md")

    with pytest.raises(MigrationError, match="symlink"):
        build_manifest(tmp_path)


def test_build_manifest_rejects_a_symlinked_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write_tree(real, {"a.md": "x"})
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(MigrationError, match="symlink"):
        build_manifest(link)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_reports_pending_work_and_writes_nothing(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    old_package = make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {"agent": AGENT, LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"},
    )
    before = build_manifest(agents_root)
    profile_before = profile.read_text(encoding="utf-8")

    report = migrate(request_for(tmp_path, profiles=(profile,), dry_run=True), filesets)

    assert report.outcome is Outcome.PENDING
    assert build_manifest(agents_root) == before
    assert profile.read_text(encoding="utf-8") == profile_before
    assert old_package.is_dir()
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert filesets.uploads == []
    assert filesets.creates == []
    assert filesets.deletes == []
    assert not journal_dir(WORKSPACE, AGENT).exists()


def strand_a_journal(tmp_path: Path, filesets: FakeFilesets) -> None:
    """Leave a real recovery-required journal behind, then clear the injection.

    The old Fileset is deleted and its restore is made to fail, which is the one
    state that keeps the journal: compensation could not finish.
    """
    filesets.fail_upload.add(LEGACY_PACKAGE)
    with pytest.MonkeyPatch.context() as patch:
        fail_remove_tree(patch, tmp_path / "agents" / LEGACY_PACKAGE)
        with pytest.raises(RecoveryRequired):
            migrate(request_for(tmp_path), filesets)
    filesets.fail_upload.discard(LEGACY_PACKAGE)


def test_dry_run_reports_a_pending_recovery_without_writing(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    strand_a_journal(tmp_path, filesets)
    journal_before = (journal_dir(WORKSPACE, AGENT) / "journal.json").read_bytes()
    uploads_before = list(filesets.uploads)

    report = migrate(request_for(tmp_path, dry_run=True), filesets)
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.RECOVERY_REQUIRED
    assert not report.ok
    assert "journal" in output
    assert "Recovery must finish" in output
    assert (journal_dir(WORKSPACE, AGENT) / "journal.json").read_bytes() == journal_before
    assert filesets.uploads == uploads_before


def test_dry_run_prints_the_affected_set_and_its_discovery_limit(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "custom" / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    experiment_dir = tmp_path / "runs" / "one"
    experiment_dir.mkdir(parents=True)

    report = migrate(
        request_for(tmp_path, profiles=(profile,), experiment_dirs=(experiment_dir,), dry_run=True),
        FakeFilesets(),
    )
    output = "\n".join(report.lines)

    assert str(profile) in output
    assert str(experiment_dir) in output
    assert str(agents_root / LEGACY_PACKAGE) in output
    assert str(agents_root / TARGET_PACKAGE) in output
    assert LEGACY_PACKAGE in output and TARGET_PACKAGE in output
    assert "cannot be discovered" in output


def test_dry_run_discovers_a_profile_by_walking_up_from_the_start_dir(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    request = MigrationRequest(
        agent=AGENT, workspace=WORKSPACE, agents_root=agents_root, dry_run=True, start_dir=nested
    )
    report = run_migration(request, filesets=FakeFilesets(), jobs=FakeJobs())

    assert str(profile) in "\n".join(report.lines)


def test_dry_run_reports_a_package_local_profile_at_its_target_path(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_profile(package / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})

    report = migrate(request_for(tmp_path, dry_run=True), FakeFilesets())
    output = "\n".join(report.lines)

    assert str(agents_root / TARGET_PACKAGE / "optimizer.yaml") in output
    assert "rewritten inside the target package" in output


def test_dry_run_deduplicates_two_spellings_of_one_profile(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    alias = tmp_path / "agents" / ".." / "optimizer.yaml"

    report = migrate(request_for(tmp_path, profiles=(profile, alias), dry_run=True), FakeFilesets())

    assert "\n".join(report.lines).count(str(profile.resolve())) == 1


# ---------------------------------------------------------------------------
# Migration from each legacy source shape
# ---------------------------------------------------------------------------


def assert_target_package_is_complete(agents_root: Path, filesets: FakeFilesets) -> None:
    target = agents_root / TARGET_PACKAGE
    assert (target / "ETHOS.md").read_text(encoding="utf-8") == target_contract()
    assert (target / "agent.yaml").read_text(encoding="utf-8") == "config_format: nemo-agents-spec-v1\nname: acme-bot\n"
    assert (target / "data" / "logo.bin").read_bytes() == b"\x00\x01\x02\xff\xfe"
    assert not (target / LEGACY_CONTRACT_FILENAME).exists()
    assert not (agents_root / LEGACY_PACKAGE).exists()

    remote = filesets.trees[(WORKSPACE, TARGET_PACKAGE)]
    assert remote["ETHOS.md"].decode("utf-8") == target_contract()
    assert remote["data/logo.bin"] == b"\x00\x01\x02\xff\xfe"
    assert LEGACY_CONTRACT_FILENAME not in remote
    assert (WORKSPACE, LEGACY_PACKAGE) not in filesets.trees


def test_migrates_a_local_only_legacy_package(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert_target_package_is_complete(agents_root, filesets)


def test_migrates_a_fileset_only_legacy_source(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert_target_package_is_complete(agents_root, filesets)


def test_migrates_equal_dual_sources_as_one_copy(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert_target_package_is_complete(agents_root, filesets)


def test_merges_paths_present_in_only_one_legacy_source(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_tree(package, {"local-only.txt": "from local"})
    remote = as_fileset_tree(legacy_package_files())
    remote["remote-only.txt"] = b"from remote"
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, remote)

    migrate(request_for(tmp_path), filesets)

    target = agents_root / TARGET_PACKAGE
    assert (target / "local-only.txt").read_text(encoding="utf-8") == "from local"
    assert (target / "remote-only.txt").read_text(encoding="utf-8") == "from remote"


def test_divergent_legacy_sources_conflict_before_any_write(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_tree(package, {"agent.yaml": "config_format: nemo-agents-spec-v1\nname: local-wins\n"})
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    before = build_manifest(agents_root)

    report = migrate(request_for(tmp_path), filesets)
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert not report.ok
    assert "agent.yaml" in output
    assert build_manifest(agents_root) == before
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_migration_preserves_all_thirteen_section_bodies(tmp_path: Path) -> None:
    from nemo_agents_plugin.ethos_parse import parse_ethos

    agents_root = tmp_path / "agents"
    make_local_package(agents_root)

    migrate(request_for(tmp_path), FakeFilesets())

    ethos = parse_ethos((agents_root / TARGET_PACKAGE / "ETHOS.md").read_text(encoding="utf-8"))
    for title in SECTION_TITLES:
        assert ethos.sections[title] == section_body(title)


def test_migration_stops_on_an_unrewritable_legacy_literal(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_tree(package, {"skills/triage/SKILL.md": "Read AGENT-SPEC.md before triaging.\n"})

    report = migrate(request_for(tmp_path), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert "skills/triage/SKILL.md" in output
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_a_legacy_literal_in_a_section_body_stops_instead_of_being_rewritten(tmp_path: Path) -> None:
    """Only the pre-section identity text is rewritten, so a body literal must stop the run."""
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    contract = legacy_contract().replace(section_body("Behavior"), "Follow the rules in AGENT-SPEC.md exactly.")
    write_tree(package, {LEGACY_CONTRACT_FILENAME: contract})

    report = migrate(request_for(tmp_path), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert "ETHOS.md" in output
    assert not (agents_root / TARGET_PACKAGE).exists()


# ---------------------------------------------------------------------------
# Package-local profiles
# ---------------------------------------------------------------------------


def test_a_package_local_profile_is_converted_inside_the_target(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_profile(
        package / "optimizer.yaml",
        {"agent": AGENT, LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}", "seed": 7},
    )
    filesets = FakeFilesets()

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.MIGRATED
    moved = agents_root / TARGET_PACKAGE / "optimizer.yaml"
    data = yaml.safe_load(moved.read_text(encoding="utf-8"))
    assert LEGACY_PROFILE_KEY not in data
    assert data["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"
    assert list(data) == ["agent", "ethos", "seed"]
    assert data["seed"] == 7
    assert not (agents_root / LEGACY_PACKAGE).exists()
    remote = filesets.trees[(WORKSPACE, TARGET_PACKAGE)]["optimizer.yaml"].decode("utf-8")
    assert LEGACY_PROFILE_KEY not in remote
    assert "ethos:" in remote


def test_a_package_local_profile_in_a_subdirectory_is_converted(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    write_profile(package / "tuning" / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})

    report = migrate(request_for(tmp_path), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED
    data = yaml.safe_load((agents_root / TARGET_PACKAGE / "tuning" / "optimizer.yaml").read_text(encoding="utf-8"))
    assert data == {"ethos": "ETHOS.md"}


def test_a_package_local_profile_is_never_rewritten_in_the_legacy_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    profile = write_profile(package / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    before = profile.read_bytes()
    old_manifest = build_manifest(package)
    fail_remove_tree(monkeypatch, package)

    with pytest.raises(MigrationError, match="delete-old-package"):
        migrate(request_for(tmp_path), FakeFilesets())

    assert profile.read_bytes() == before
    assert build_manifest(package) == old_manifest


def test_an_explicit_profile_inside_the_package_is_treated_as_package_local(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    profile = write_profile(package / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.MIGRATED
    assert "External profiles rewritten in place (0)" in output
    assert (agents_root / TARGET_PACKAGE / "optimizer.yaml").is_file()


# ---------------------------------------------------------------------------
# External profile rewrite
# ---------------------------------------------------------------------------


def test_rewrites_the_profile_key_and_path_and_keeps_unrelated_keys_in_order(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {
            "agent": AGENT,
            LEGACY_PROFILE_KEY: f"agents/{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}",
            "datasets": {"train": "data/train.jsonl"},
            "base_url": "http://localhost:8080",
        },
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert LEGACY_PROFILE_KEY not in data
    assert data["ethos"] == f"agents/{TARGET_PACKAGE}/ETHOS.md"
    assert list(data) == ["agent", "ethos", "datasets", "base_url"]
    assert data["datasets"] == {"train": "data/train.jsonl"}
    assert data["base_url"] == "http://localhost:8080"


def test_rewrites_a_bare_contract_filename_in_the_profile(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})

    migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert yaml.safe_load(profile.read_text(encoding="utf-8"))["ethos"] == "ETHOS.md"


def test_profile_without_either_key_is_left_byte_for_byte(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent": AGENT, "datasets": {"train": "t.jsonl"}})
    before = profile.read_bytes()

    migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert profile.read_bytes() == before


def test_conflicting_old_and_new_profile_keys_stop_the_command(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}", "ethos": "somewhere/else/ETHOS.md"},
    )
    before = profile.read_bytes()

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert str(profile) in output
    assert "somewhere/else/ETHOS.md" in output
    assert profile.read_bytes() == before
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_half_converted_profile_keys_that_agree_are_not_a_conflict(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}", "ethos": f"{TARGET_PACKAGE}/ETHOS.md"},
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert LEGACY_PROFILE_KEY not in data
    assert data["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"


def test_profile_value_without_a_known_rewrite_stops_the_command(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: "docs/README.md"})

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert "docs/README.md" in output


def test_a_null_legacy_profile_key_is_a_conflict_not_an_absent_key(tmp_path: Path) -> None:
    """A present-but-empty key is malformed, and treating it as absent would skip it."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = tmp_path / "optimizer.yaml"
    profile.write_text(f"agent: {AGENT}\n{LEGACY_PROFILE_KEY}:\n", encoding="utf-8")
    before = profile.read_bytes()

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert str(profile) in output
    assert "string path" in output
    assert profile.read_bytes() == before
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_a_null_ethos_key_is_a_conflict(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = tmp_path / "optimizer.yaml"
    profile.write_text("ethos:\n", encoding="utf-8")

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.CONFLICT
    assert "string path" in "\n".join(report.lines)


def test_a_profile_written_to_the_wrong_target_value_fails_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verification demands the exact computed value, not merely an ETHOS.md suffix."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    profile_before = profile.read_bytes()
    real = ethos_migrate._write_profile

    def wrong_value(path: Path, payload: dict[str, Any]) -> None:
        real(path, {"ethos": "some-other-agent-ethos/ETHOS.md"} if path == profile else payload)

    monkeypatch.setattr(ethos_migrate, "_write_profile", wrong_value)

    with pytest.raises(MigrationError, match="rewrite-profiles"):
        migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert profile.read_bytes() == profile_before
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees


# ---------------------------------------------------------------------------
# State classification
# ---------------------------------------------------------------------------


def make_target_package(
    agents_root: Path, filesets: FakeFilesets, *, complete: bool = True, extra: dict[str, bytes | str] | None = None
) -> None:
    """Write the exact output a successful migration leaves behind."""
    files: dict[str, bytes | str] = {
        "ETHOS.md": target_contract(),
        "agent.yaml": "config_format: nemo-agents-spec-v1\nname: acme-bot\n",
        "skills/triage/SKILL.md": "# Triage skill\n\nagent-specific guidance.\n",
        "data/logo.bin": b"\x00\x01\x02\xff\xfe",
    }
    if not complete:
        files.pop("data/logo.bin")
    if extra:
        files.update(extra)
    write_tree(agents_root / TARGET_PACKAGE, files)
    filesets.seed(TARGET_PACKAGE, as_fileset_tree(files))


def test_no_sources_and_no_target_is_a_read_only_no_op(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()

    report = migrate(request_for(tmp_path), FakeFilesets())

    assert report.outcome is Outcome.NOTHING_TO_MIGRATE
    assert report.ok
    assert "nothing was written" in "\n".join(report.lines)
    # Truly read-only: the empty state never even creates the lock file, because
    # the preliminary pass returns before any path that could mutate.
    assert not journal_dir(WORKSPACE, AGENT).exists()


def test_target_only_with_converted_profiles_is_idempotent_success(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets)
    profile = write_profile(tmp_path / "optimizer.yaml", {"ethos": f"{TARGET_PACKAGE}/ETHOS.md"})
    before = profile.read_bytes()

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.ALREADY_MIGRATED
    assert profile.read_bytes() == before
    assert filesets.uploads == []
    assert filesets.creates == []
    assert filesets.deletes == []


def test_target_only_with_an_old_profile_resumes_profile_conversion(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets)
    profile = write_profile(
        tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"}
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert yaml.safe_load(profile.read_text(encoding="utf-8"))["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"


def test_a_target_only_leftover_literal_outside_the_contract_is_a_conflict(tmp_path: Path) -> None:
    """Every target text file is scanned, not only ETHOS.md."""
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets, extra={"skills/triage/NOTES.md": "See AGENT-SPEC.md for context.\n"})
    profile = write_profile(tmp_path / "optimizer.yaml", {"ethos": f"{TARGET_PACKAGE}/ETHOS.md"})
    before = build_manifest(agents_root / TARGET_PACKAGE)

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert "still names the pre-rename" in "\n".join(report.lines)
    assert build_manifest(agents_root / TARGET_PACKAGE) == before
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_a_target_only_package_local_profile_still_naming_the_old_key_is_a_conflict(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(
        agents_root, filesets, extra={"optimizer.yaml": f"{LEGACY_PROFILE_KEY}: {LEGACY_CONTRACT_FILENAME}\n"}
    )

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_legacy_plus_equal_target_with_old_profile_finishes_the_move(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    profile = write_profile(
        tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"}
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert_target_package_is_complete(agents_root, filesets)
    assert yaml.safe_load(profile.read_text(encoding="utf-8"))["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"


def test_legacy_plus_equal_target_with_converted_profiles_resumes_cleanup(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    profile = write_profile(tmp_path / "optimizer.yaml", {"ethos": f"{TARGET_PACKAGE}/ETHOS.md"})

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert_target_package_is_complete(agents_root, filesets)


def test_legacy_plus_divergent_target_is_a_conflict(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets)
    write_tree(agents_root / TARGET_PACKAGE, {"agent.yaml": "config_format: nemo-agents-spec-v1\nname: drifted\n"})
    before = build_manifest(agents_root)

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert build_manifest(agents_root) == before
    assert (agents_root / LEGACY_PACKAGE).is_dir()
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_partial_target_with_no_legacy_source_is_a_conflict(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets, complete=False)
    del filesets.trees[(WORKSPACE, TARGET_PACKAGE)]

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert filesets.uploads == []


def test_a_target_whose_two_copies_disagree_is_a_conflict(tmp_path: Path) -> None:
    """Completeness means matching checksums, not merely that both copies exist."""
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets)
    filesets.trees[(WORKSPACE, TARGET_PACKAGE)]["agent.yaml"] = b"config_format: nemo-agents-spec-v1\nname: drifted\n"
    profile = write_profile(tmp_path / "optimizer.yaml", {"ethos": f"{TARGET_PACKAGE}/ETHOS.md"})
    target_before = build_manifest(agents_root / TARGET_PACKAGE)

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.CONFLICT
    assert build_manifest(agents_root / TARGET_PACKAGE) == target_before
    assert filesets.uploads == []
    assert filesets.deletes == []


def test_stale_profile_reference_with_no_package_state_is_a_conflict(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    profile = write_profile(
        tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"}
    )
    before = profile.read_bytes()

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.CONFLICT
    assert str(profile) in "\n".join(report.lines)
    assert profile.read_bytes() == before


# ---------------------------------------------------------------------------
# Active-work gates
# ---------------------------------------------------------------------------


def insights_job(*, status: str, agent: str = AGENT, source: str = "insights", name: str = "job-1") -> JobRecord:
    return JobRecord(name=name, workspace=WORKSPACE, source=source, status=status, spec={"agent": agent})


def test_a_nonterminal_matching_insights_job_blocks_migration(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    jobs = FakeJobs([insights_job(status="active", name="analyze-run-7")])

    report = migrate(request_for(tmp_path), FakeFilesets(), jobs)
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.BLOCKED
    assert "analyze-run-7" in output
    assert "active" in output
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert (agents_root / LEGACY_PACKAGE).is_dir()


@pytest.mark.parametrize("status", ["completed", "error", "cancelled"])
def test_terminal_insights_jobs_do_not_block(tmp_path: Path, status: str) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    jobs = FakeJobs([insights_job(status=status)])

    report = migrate(request_for(tmp_path), FakeFilesets(), jobs)

    assert report.outcome is Outcome.MIGRATED


def test_an_unrecognized_job_status_blocks(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    jobs = FakeJobs([insights_job(status="who-knows")])

    report = migrate(request_for(tmp_path), FakeFilesets(), jobs)

    assert report.outcome is Outcome.BLOCKED


def test_a_nonterminal_job_for_another_agent_or_source_does_not_block(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    jobs = FakeJobs(
        [
            insights_job(status="active", agent="other-bot", name="other-agent"),
            insights_job(status="active", source="evaluator", name="other-source"),
        ]
    )

    report = migrate(request_for(tmp_path), FakeFilesets(), jobs)

    assert report.outcome is Outcome.MIGRATED


def write_experiment_run(
    directory: Path, *, status: str | None, candidates: int = 1, run_json: str | None = None
) -> Path:
    eo = directory / EXPERIMENT_DIRNAME
    eo.mkdir(parents=True, exist_ok=True)
    if run_json is not None:
        (eo / "run.json").write_text(run_json, encoding="utf-8")
    elif status is not None:
        (eo / "run.json").write_text(json.dumps({"agent": AGENT, "status": status}), encoding="utf-8")
    for index in range(candidates):
        candidate = eo / "candidates" / f"cand-{index}.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(json.dumps({"id": f"cand-{index}"}), encoding="utf-8")
    return directory


EXPERIMENT_DIRNAME = "eval-and-optimize"


@pytest.mark.parametrize("status", ["running", "failed", "paused", "who-knows"])
def test_any_non_completed_experiment_run_blocks_migration(tmp_path: Path, status: str) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "live", status=status)

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.BLOCKED
    assert str(experiment_dir) in output
    assert status in output
    assert (agents_root / LEGACY_PACKAGE).is_dir()


def test_a_completed_experiment_run_is_historical_and_does_not_block(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "done", status="completed")

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED


def test_a_run_json_with_no_status_blocks(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "statusless", status=None, run_json="{}")

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.BLOCKED
    assert "no status" in output


def test_a_non_object_run_json_blocks(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "listy", status=None, run_json='["running"]')

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.BLOCKED
    assert "not an object" in output


def test_a_malformed_run_json_beside_candidates_blocks_migration(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "broken", status=None, run_json="{not json")

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())

    assert report.outcome is Outcome.BLOCKED
    assert str(experiment_dir) in "\n".join(report.lines)


def test_a_missing_run_json_beside_candidates_blocks_migration(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "orphaned", status=None)

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())

    assert report.outcome is Outcome.BLOCKED


def test_candidateless_directories_never_block(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    experiment_dir = write_experiment_run(tmp_path / "runs" / "empty", status="running", candidates=0)

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED


def test_profile_derived_experiment_directories_are_checked(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    derived = write_experiment_run(tmp_path / ".nemo-optimizer" / "experiments" / "run-a", status="running")

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.BLOCKED
    assert str(derived) in "\n".join(report.lines)


def test_gates_do_not_run_when_there_is_nothing_to_migrate(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    jobs = FakeJobs([insights_job(status="active")])
    experiment_dir = write_experiment_run(tmp_path / "runs" / "live", status="running")

    report = migrate(request_for(tmp_path, experiment_dirs=(experiment_dir,)), FakeFilesets(), jobs)

    assert report.outcome is Outcome.NOTHING_TO_MIGRATE


# ---------------------------------------------------------------------------
# Target ownership races
# ---------------------------------------------------------------------------


def test_a_target_fileset_that_appears_mid_run_is_not_adopted_or_deleted(tmp_path: Path) -> None:
    """Conditional create decides ownership, so another writer's Fileset survives."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.steal_on_create[TARGET_PACKAGE] = {"other-writer.txt": b"mine"}
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)

    with pytest.raises(MigrationError, match="another writer"):
        migrate(request_for(tmp_path), filesets)

    assert filesets.trees[(WORKSPACE, TARGET_PACKAGE)] == {"other-writer.txt": b"mine"}
    assert filesets.deletes == []
    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_a_target_package_that_appears_mid_run_is_not_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    target = agents_root / TARGET_PACKAGE
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    real = ethos_migrate._copy_tree

    def racing(source: Path, destination: Path) -> None:
        if destination == target:
            write_tree(destination, {"other-writer.txt": "mine"})
        real(source, destination)

    monkeypatch.setattr(ethos_migrate, "_copy_tree", racing)

    with pytest.raises(MigrationError, match="another writer"):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(target) == {"other-writer.txt": build_manifest(target)["other-writer.txt"]}
    assert (target / "other-writer.txt").read_text(encoding="utf-8") == "mine"
    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees


def test_a_target_fileset_this_run_did_not_create_is_never_deleted_on_failure(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    remote_before = dict(filesets.trees[(WORKSPACE, TARGET_PACKAGE)])
    filesets.fail_delete.add(LEGACY_PACKAGE)

    with pytest.raises(MigrationError, match="delete-old-fileset"):
        migrate(request_for(tmp_path), filesets)

    assert filesets.trees[(WORKSPACE, TARGET_PACKAGE)] == remote_before
    assert TARGET_PACKAGE not in filesets.deletes
    assert (agents_root / TARGET_PACKAGE).is_dir()


def test_the_target_fileset_is_created_before_it_is_uploaded_into(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()

    migrate(request_for(tmp_path), filesets)

    assert filesets.creates == [TARGET_PACKAGE]
    assert filesets.uploads == [TARGET_PACKAGE]


# ---------------------------------------------------------------------------
# Transaction ordering, compensation, and recovery
# ---------------------------------------------------------------------------


def test_the_old_state_stays_authoritative_until_the_target_is_verified(tmp_path: Path) -> None:
    """Observe real state at each Fileset boundary, which is the ordering contract."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    profile_before = profile.read_bytes()
    observed: list[tuple[str, str, bool, bool]] = []

    def observe(operation: str, name: str) -> None:
        observed.append(
            (
                operation,
                name,
                (agents_root / LEGACY_PACKAGE).is_dir(),
                profile.read_bytes() == profile_before,
            )
        )

    filesets.observer = observe
    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.MIGRATED
    # Creating and filling the target happens while the old package and the old
    # profile key are both still intact.
    assert ("create", TARGET_PACKAGE, True, True) in observed
    assert ("upload", TARGET_PACKAGE, True, True) in observed
    # The old Fileset is only deleted after the profiles have been converted,
    # which means the target was already written and verified.
    assert ("delete", LEGACY_PACKAGE, True, False) in observed
    assert [entry[:2] for entry in observed].index(("delete", LEGACY_PACKAGE)) > [
        entry[:2] for entry in observed
    ].index(("upload", TARGET_PACKAGE))


@pytest.mark.parametrize("failing_step", MUTATING_STEPS)
def test_a_failure_at_each_step_restores_the_old_authoritative_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {"agent": AGENT, LEGACY_PROFILE_KEY: f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"},
    )
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    profile_before = profile.read_bytes()
    inject_step_failure(monkeypatch, failing_step, filesets=filesets, agents_root=agents_root, profile=profile)

    with pytest.raises(MigrationError, match=failing_step):
        migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote
    assert profile.read_bytes() == profile_before
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()
    assert not (journal_dir(WORKSPACE, AGENT) / "backup").exists()


def test_a_pre_existing_equal_target_survives_a_failed_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    target_before = build_manifest(agents_root / TARGET_PACKAGE)
    remote_before = dict(filesets.trees[(WORKSPACE, TARGET_PACKAGE)])
    fail_verify_final(monkeypatch, RuntimeError("injected final-verify failure"))

    with pytest.raises(MigrationError):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root / TARGET_PACKAGE) == target_before
    assert filesets.trees[(WORKSPACE, TARGET_PACKAGE)] == remote_before
    assert (agents_root / LEGACY_PACKAGE).is_dir()


def test_a_failure_between_the_two_deletions_restores_both_legacy_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    fail_remove_tree(monkeypatch, agents_root / LEGACY_PACKAGE)

    with pytest.raises(MigrationError, match="delete-old-package"):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote


def test_a_failed_compensation_keeps_the_journal_and_reports_recovery_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    filesets.fail_upload.add(LEGACY_PACKAGE)
    fail_remove_tree(monkeypatch, agents_root / LEGACY_PACKAGE)

    with pytest.raises(RecoveryRequired, match="recovery-required"):
        migrate(request_for(tmp_path), filesets)

    assert (journal_dir(WORKSPACE, AGENT) / "journal.json").is_file()


def test_a_second_apply_recovers_before_starting_new_work(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    strand_a_journal(tmp_path, filesets)

    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.RECOVERED
    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_recovery_ignores_new_arguments_and_touches_only_recorded_paths(tmp_path: Path) -> None:
    """A rerun cannot redirect recovery at a path the failed run never touched.

    The failed run gets far enough to delete both legacy copies and then cannot
    restore them, so recovery has real writes to place. The second invocation
    names a different agents root whose package holds different bytes, so a
    recovery that followed the new arguments would be visible either as a broken
    restore or as a changed decoy.
    """
    recorded_root = tmp_path / "agents"
    make_local_package(recorded_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    recorded_manifest = build_manifest(recorded_root / LEGACY_PACKAGE)

    with pytest.MonkeyPatch.context() as patch:
        fail_verify_final(patch, RuntimeError("injected final-verify failure"))
        fail_copy_tree_into(patch, recorded_root / LEGACY_PACKAGE)
        with pytest.raises(RecoveryRequired):
            migrate(request_for(tmp_path), filesets)

    assert not (recorded_root / LEGACY_PACKAGE).exists()
    assert (WORKSPACE, LEGACY_PACKAGE) not in filesets.trees

    # A second invocation naming completely different paths, whose package holds
    # different bytes than the recorded one.
    decoy_root = tmp_path / "other-agents"
    decoy_package = decoy_root / LEGACY_PACKAGE
    write_tree(decoy_package, {"decoy.txt": "do not touch"})
    decoy_manifest = build_manifest(decoy_package)
    decoy_profile = write_profile(tmp_path / "decoy" / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})
    decoy_profile_before = decoy_profile.read_bytes()
    decoy_experiments = write_experiment_run(tmp_path / "decoy-runs" / "live", status="running")

    report = migrate(
        request_for(
            tmp_path,
            agents_root=decoy_root,
            profiles=(decoy_profile,),
            experiment_dirs=(decoy_experiments,),
        ),
        filesets,
    )

    assert report.outcome is Outcome.RECOVERED
    # The recorded package and Fileset were restored; nothing the new arguments named moved.
    assert build_manifest(recorded_root / LEGACY_PACKAGE) == recorded_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == as_fileset_tree(legacy_package_files())
    assert build_manifest(decoy_package) == decoy_manifest
    assert decoy_profile.read_bytes() == decoy_profile_before
    assert not (decoy_root / TARGET_PACKAGE).exists()
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_a_journal_whose_target_is_committed_finishes_cleanup(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    profile = write_profile(tmp_path / "optimizer.yaml", {LEGACY_PROFILE_KEY: LEGACY_CONTRACT_FILENAME})

    with pytest.MonkeyPatch.context() as patch:
        fail_verify_final(patch, KeyboardInterrupt("process killed after both deletions"))
        with pytest.raises(KeyboardInterrupt):
            migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert (journal_dir(WORKSPACE, AGENT) / "journal.json").is_file()

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.RECOVERED
    assert_target_package_is_complete(agents_root, filesets)
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_an_unreadable_journal_reports_recovery_required(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    directory = journal_dir(WORKSPACE, AGENT)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "journal.json").write_text("{not json", encoding="utf-8")
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)

    with pytest.raises(RecoveryRequired, match="recovery-required"):
        migrate(request_for(tmp_path), FakeFilesets())

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest


# ---------------------------------------------------------------------------
# Journal-write failures
# ---------------------------------------------------------------------------


def test_a_journal_write_failure_before_any_mutation_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    fail_journal_writes_from(monkeypatch, 1)

    with pytest.raises(MigrationError, match="backups"):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.creates == []
    assert filesets.uploads == []
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_a_journal_write_failure_after_a_mutation_still_compensates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compensation runs from the in-memory record, so a failed journal write cannot skip it."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    # Calls: 1 initial, 2 finish(backups), 3 after the target Fileset is created.
    fail_journal_writes_from(monkeypatch, 3)

    with pytest.raises(MigrationError, match="upload-target-fileset"):
        migrate(request_for(tmp_path), filesets)

    assert filesets.creates == [TARGET_PACKAGE]
    # The Fileset this run created was rolled back even though the journal write failed.
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees
    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_a_journal_write_failure_does_not_mask_a_failed_compensation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.fail_delete.add(TARGET_PACKAGE)
    fail_journal_writes_from(monkeypatch, 3)

    with pytest.raises(RecoveryRequired, match="recovery-required"):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root / LEGACY_PACKAGE) is not None


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


def test_lock_contention_stops_a_mutating_apply(tmp_path: Path) -> None:
    import fcntl

    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    directory = journal_dir(WORKSPACE, AGENT)
    directory.mkdir(parents=True, exist_ok=True)
    before = build_manifest(agents_root)

    with (directory / "lock").open("w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MigrationError, match="already running"):
            migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root) == before
    assert filesets.creates == []
    assert filesets.uploads == []
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_lock_contention_stops_a_recovery(tmp_path: Path) -> None:
    import fcntl

    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    strand_a_journal(tmp_path, filesets)
    directory = journal_dir(WORKSPACE, AGENT)
    journal_before = (directory / "journal.json").read_bytes()

    with (directory / "lock").open("w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MigrationError, match="already running"):
            migrate(request_for(tmp_path), filesets)

    assert (directory / "journal.json").read_bytes() == journal_before


def test_a_dry_run_never_takes_the_lock(tmp_path: Path) -> None:
    import fcntl

    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    directory = journal_dir(WORKSPACE, AGENT)
    directory.mkdir(parents=True, exist_ok=True)

    with (directory / "lock").open("w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = migrate(request_for(tmp_path, dry_run=True), FakeFilesets())

    assert report.outcome is Outcome.PENDING


def test_the_journal_lives_outside_the_agents_root(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    assert not journal_dir(WORKSPACE, AGENT).is_relative_to(agents_root)
    assert journal_dir(WORKSPACE, AGENT) != journal_dir(WORKSPACE, f"{AGENT}-x")
    assert journal_dir("a", "b-c") != journal_dir("a-b", "c")


# ---------------------------------------------------------------------------
# SDK adapters
# ---------------------------------------------------------------------------


def not_found_error() -> Exception:
    from nemo_platform import NotFoundError

    return NotFoundError("missing", response=MagicMock(), body=None)


def conflict_error() -> Exception:
    from nemo_platform import ConflictError

    return ConflictError("exists", response=MagicMock(), body=None)


class StubFilesetsResource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.retrieve_error: Exception | None = None
        self.create_error: Exception | None = None

    def retrieve(self, name: str, **kwargs: Any) -> Any:
        self.calls.append(("retrieve", (name,), kwargs))
        if self.retrieve_error is not None:
            raise self.retrieve_error
        return object()

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(("create", (), kwargs))
        if self.create_error is not None:
            raise self.create_error
        return object()

    def delete(self, name: str, **kwargs: Any) -> Any:
        self.calls.append(("delete", (name,), kwargs))
        return object()


class StubFilesResource:
    def __init__(self) -> None:
        self.filesets = StubFilesetsResource()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def download(self, **kwargs: Any) -> None:
        self.calls.append(("download", kwargs))

    def upload(self, **kwargs: Any) -> Any:
        self.calls.append(("upload", kwargs))
        return MagicMock(name="fileset")


class StubJobsResource:
    # ``pages`` is annotated with ``Sequence`` because the ``list`` method below
    # shadows the builtin inside this class body.
    def __init__(self, pages: Sequence[Any]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return iter(self.pages)


class StubSdk:
    def __init__(self, *, jobs_pages: list[Any] | None = None) -> None:
        self.files = StubFilesResource()
        self.jobs = StubJobsResource(jobs_pages or [])


def test_sdk_fileset_store_exists_uses_retrieve_and_maps_not_found() -> None:
    sdk = StubSdk()
    store = SdkFilesetStore(sdk)

    assert store.exists(workspace=WORKSPACE, name=TARGET_PACKAGE) is True
    assert sdk.files.filesets.calls == [("retrieve", (TARGET_PACKAGE,), {"workspace": WORKSPACE})]

    sdk.files.filesets.retrieve_error = not_found_error()
    assert store.exists(workspace=WORKSPACE, name=TARGET_PACKAGE) is False


def test_sdk_fileset_store_exists_maps_the_plugin_client_not_found() -> None:
    from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError

    sdk = StubSdk()
    sdk.files.filesets.retrieve_error = PluginClientNotFoundError(MagicMock())

    assert SdkFilesetStore(sdk).exists(workspace=WORKSPACE, name=TARGET_PACKAGE) is False


def test_sdk_fileset_store_create_is_conditional() -> None:
    sdk = StubSdk()
    store = SdkFilesetStore(sdk)

    assert store.create(workspace=WORKSPACE, name=TARGET_PACKAGE) is True
    operation, args, kwargs = sdk.files.filesets.calls[-1]
    assert operation == "create"
    assert args == ()
    assert kwargs == {"name": TARGET_PACKAGE, "workspace": WORKSPACE}
    # exist_ok must stay at its default of False, or a 409 would look like a create.
    assert "exist_ok" not in kwargs

    sdk.files.filesets.create_error = conflict_error()
    assert store.create(workspace=WORKSPACE, name=TARGET_PACKAGE) is False


def test_sdk_fileset_store_create_propagates_other_errors() -> None:
    sdk = StubSdk()
    sdk.files.filesets.create_error = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        SdkFilesetStore(sdk).create(workspace=WORKSPACE, name=TARGET_PACKAGE)


def test_sdk_fileset_store_download_creates_the_destination(tmp_path: Path) -> None:
    sdk = StubSdk()
    dest = tmp_path / "nested" / "dest"

    SdkFilesetStore(sdk).download(workspace=WORKSPACE, name=TARGET_PACKAGE, dest=dest)

    assert dest.is_dir()
    assert sdk.files.calls == [
        ("download", {"local_path": str(dest), "fileset": TARGET_PACKAGE, "workspace": WORKSPACE})
    ]


def test_sdk_fileset_store_upload_sends_contents_and_disables_auto_create(tmp_path: Path) -> None:
    sdk = StubSdk()
    source = tmp_path / "staged"
    source.mkdir()

    SdkFilesetStore(sdk).upload(workspace=WORKSPACE, name=TARGET_PACKAGE, source=source)

    operation, kwargs = sdk.files.calls[-1]
    assert operation == "upload"
    assert kwargs["local_path"] == f"{source}/"
    assert kwargs["fileset"] == TARGET_PACKAGE
    assert kwargs["workspace"] == WORKSPACE
    assert kwargs["fileset_auto_create"] is False


def test_sdk_fileset_store_delete_passes_the_name_and_workspace() -> None:
    sdk = StubSdk()

    SdkFilesetStore(sdk).delete(workspace=WORKSPACE, name=LEGACY_PACKAGE)

    assert sdk.files.filesets.calls == [("delete", (LEGACY_PACKAGE,), {"workspace": WORKSPACE})]


def test_sdk_job_store_iterates_pages_and_converts_status() -> None:
    from nemo_platform_plugin.jobs.schemas import PlatformJobStatus

    first = MagicMock()
    first.name = "analyze-1"
    first.workspace = WORKSPACE
    first.source = "insights"
    first.status = PlatformJobStatus.COMPLETED
    first.spec = {"agent": AGENT}

    second = MagicMock()
    second.name = "analyze-2"
    second.workspace = WORKSPACE
    second.source = "insights"
    second.status = PlatformJobStatus.ACTIVE
    second.spec = None

    sdk = StubSdk(jobs_pages=[first, second])
    records = SdkJobStore(sdk).list_jobs(workspace=WORKSPACE)

    assert sdk.jobs.calls == [{"workspace": WORKSPACE}]
    assert [record.name for record in records] == ["analyze-1", "analyze-2"]
    assert records[0].status == "completed"
    assert records[1].status == "active"
    assert records[0].spec == {"agent": AGENT}
    assert records[1].spec == {}


def test_sdk_job_store_tolerates_a_plain_string_status() -> None:
    job = MagicMock()
    job.name = "analyze-3"
    job.workspace = WORKSPACE
    job.source = "insights"
    job.status = "active"
    job.spec = {"agent": AGENT}

    records = SdkJobStore(StubSdk(jobs_pages=[job])).list_jobs(workspace=WORKSPACE)

    assert records[0].status == "active"
