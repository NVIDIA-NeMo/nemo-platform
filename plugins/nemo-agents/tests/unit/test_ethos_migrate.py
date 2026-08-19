# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``nemo agents ethos migrate``.

This file and ``nemo_agents_plugin.ethos_migrate`` are the only places in the
plugin allowed to name the pre-rename artifact, because migration owns every
old-name lookup.

Filesets and Jobs are covered by small in-memory fakes that hold real bytes, so
manifest, parser, profile, and transaction behavior is exercised against real
files on disk rather than call-count assertions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from nemo_agents_plugin.cli import AgentsCLI
from nemo_agents_plugin.ethos_migrate import (
    JobRecord,
    MigrationError,
    MigrationRequest,
    Outcome,
    RecoveryRequired,
    build_manifest,
    journal_dir,
    run_migration,
)
from typer.testing import CliRunner

AGENT = "acme-bot"
WORKSPACE = "default"

LEGACY_CONTRACT_FILENAME = "AGENT-SPEC.md"
LEGACY_PACKAGE = f"{AGENT}-spec"
TARGET_PACKAGE = f"{AGENT}-ethos"

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
    """In-memory Filesets holding real bytes keyed by relative POSIX path."""

    trees: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    fail_upload: set[str] = field(default_factory=set)
    drop_on_upload: dict[str, set[str]] = field(default_factory=dict)
    uploads: list[str] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)

    def seed(self, name: str, tree: dict[str, bytes], *, workspace: str = WORKSPACE) -> None:
        self.trees[(workspace, name)] = dict(tree)

    def exists(self, *, workspace: str, name: str) -> bool:
        return (workspace, name) in self.trees

    def download(self, *, workspace: str, name: str, dest: Path) -> None:
        tree = self.trees.get((workspace, name))
        if tree is None:
            raise KeyError(f"no such fileset: {workspace}/{name}")
        for rel, payload in tree.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

    def upload(self, *, workspace: str, name: str, source: Path) -> None:
        self.uploads.append(name)
        if name in self.fail_upload:
            raise OSError(f"injected upload failure for {name}")
        tree = self.trees.setdefault((workspace, name), {})
        dropped = self.drop_on_upload.get(name, set())
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source).as_posix()
            # A silently lossy upload: the platform reports success but the
            # fileset is short a file, which only a download can reveal.
            if path.is_file() and rel not in dropped:
                tree[rel] = path.read_bytes()

    def delete(self, *, workspace: str, name: str) -> None:
        self.deletes.append(name)
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
) -> MigrationRequest:
    return MigrationRequest(
        agent=AGENT,
        workspace=WORKSPACE,
        agents_root=tmp_path / "agents",
        profiles=profiles,
        experiment_dirs=experiment_dirs,
        dry_run=dry_run,
        start_dir=tmp_path / "cwd-with-no-profile",
    )


def migrate(request: MigrationRequest, filesets: FakeFilesets, jobs: FakeJobs | None = None, **kwargs):
    return run_migration(request, filesets=filesets, jobs=jobs or FakeJobs(), **kwargs)


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


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_reports_pending_work_and_writes_nothing(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    old_package = make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile = write_profile(
        tmp_path / "optimizer.yaml", {"agent": AGENT, "agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"}
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
    assert filesets.deletes == []
    assert not journal_dir(WORKSPACE, AGENT).exists()


def test_dry_run_prints_the_affected_set_and_its_discovery_limit(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "custom" / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})
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
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    request = MigrationRequest(
        agent=AGENT, workspace=WORKSPACE, agents_root=agents_root, dry_run=True, start_dir=nested
    )
    report = run_migration(request, filesets=FakeFilesets(), jobs=FakeJobs())

    assert str(profile) in "\n".join(report.lines)


def test_dry_run_includes_a_profile_inside_the_legacy_package(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    package = make_local_package(agents_root)
    packaged_profile = write_profile(package / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})

    report = migrate(request_for(tmp_path, dry_run=True), FakeFilesets())

    assert str(packaged_profile.resolve()) in "\n".join(report.lines)


def test_dry_run_deduplicates_two_spellings_of_one_profile(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})
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
# Profile rewrite
# ---------------------------------------------------------------------------


def test_rewrites_the_profile_key_and_path_and_keeps_unrelated_keys_in_order(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(
        tmp_path / "optimizer.yaml",
        {
            "agent": AGENT,
            "agent_spec": f"agents/{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}",
            "datasets": {"train": "data/train.jsonl"},
            "base_url": "http://localhost:8080",
        },
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert "agent_spec" not in data
    assert data["ethos"] == f"agents/{TARGET_PACKAGE}/ETHOS.md"
    assert list(data) == ["agent", "ethos", "datasets", "base_url"]
    assert data["datasets"] == {"train": "data/train.jsonl"}
    assert data["base_url"] == "http://localhost:8080"


def test_rewrites_a_bare_contract_filename_in_the_profile(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})

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
        {"agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}", "ethos": "somewhere/else/ETHOS.md"},
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
        {"agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}", "ethos": f"{TARGET_PACKAGE}/ETHOS.md"},
    )

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())

    assert report.outcome is Outcome.MIGRATED
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert "agent_spec" not in data
    assert data["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"


def test_profile_value_without_a_known_rewrite_stops_the_command(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": "docs/README.md"})

    report = migrate(request_for(tmp_path, profiles=(profile,)), FakeFilesets())
    output = "\n".join(report.lines)

    assert report.outcome is Outcome.CONFLICT
    assert "docs/README.md" in output


# ---------------------------------------------------------------------------
# State classification
# ---------------------------------------------------------------------------


def make_target_package(agents_root: Path, filesets: FakeFilesets, *, complete: bool = True) -> None:
    """Write the exact output a successful migration leaves behind."""
    files: dict[str, bytes | str] = {
        "ETHOS.md": target_contract(),
        "agent.yaml": "config_format: nemo-agents-spec-v1\nname: acme-bot\n",
        "skills/triage/SKILL.md": "# Triage skill\n\nagent-specific guidance.\n",
        "data/logo.bin": b"\x00\x01\x02\xff\xfe",
    }
    if not complete:
        files.pop("data/logo.bin")
    write_tree(agents_root / TARGET_PACKAGE, files)
    filesets.seed(TARGET_PACKAGE, as_fileset_tree(files))


def test_no_sources_and_no_target_is_a_read_only_no_op(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()

    report = migrate(request_for(tmp_path), FakeFilesets())

    assert report.outcome is Outcome.NOTHING_TO_MIGRATE
    assert report.ok
    # An apply takes the lock before it reads anything, so the lock file is the
    # only residue a no-op leaves. No journal and no backup is created.
    assert sorted(path.name for path in journal_dir(WORKSPACE, AGENT).iterdir()) == ["lock"]


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
    assert filesets.deletes == []


def test_target_only_with_an_old_profile_resumes_profile_conversion(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    filesets = FakeFilesets()
    make_target_package(agents_root, filesets)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"})

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.MIGRATED
    assert yaml.safe_load(profile.read_text(encoding="utf-8"))["ethos"] == f"{TARGET_PACKAGE}/ETHOS.md"


def test_legacy_plus_equal_target_with_old_profile_finishes_the_move(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"})

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
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"})
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
    eo = directory / "eval-and-optimize"
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


@pytest.mark.parametrize("status", ["running", "failed"])
def test_a_resumable_experiment_run_blocks_migration(tmp_path: Path, status: str) -> None:
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
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})
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
# Transaction, compensation, and recovery
# ---------------------------------------------------------------------------

MUTATING_STEPS = (
    "upload-target-fileset",
    "verify-target-fileset",
    "write-target-package",
    "rewrite-profiles",
    "delete-old-fileset",
    "delete-old-package",
    "final-verify",
)


@pytest.mark.parametrize("failing_step", MUTATING_STEPS)
def test_a_failure_at_each_step_restores_the_old_authoritative_state(tmp_path: Path, failing_step: str) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile_payload = {"agent": AGENT, "agent_spec": f"{LEGACY_PACKAGE}/{LEGACY_CONTRACT_FILENAME}"}
    profile = write_profile(tmp_path / "optimizer.yaml", profile_payload)
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    profile_before = profile.read_bytes()

    def fault(step: str) -> None:
        if step == failing_step:
            raise RuntimeError(f"injected failure at {step}")

    with pytest.raises(MigrationError, match=failing_step):
        migrate(request_for(tmp_path, profiles=(profile,)), filesets, on_step=fault)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote
    assert profile.read_bytes() == profile_before
    assert not (agents_root / TARGET_PACKAGE).exists()
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()
    assert not (journal_dir(WORKSPACE, AGENT) / "backup").exists()


def test_the_old_state_stays_authoritative_until_the_final_verify(tmp_path: Path) -> None:
    """Observe real state at each step boundary, which is the ordering contract."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})
    profile_before = profile.read_bytes()
    observed: dict[str, dict[str, bool]] = {}

    def observe(step: str) -> None:
        observed[step] = {
            "old_package": (agents_root / LEGACY_PACKAGE).is_dir(),
            "old_fileset": filesets.exists(workspace=WORKSPACE, name=LEGACY_PACKAGE),
            "old_profile": profile.read_bytes() == profile_before,
        }

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets, on_step=observe)

    assert report.outcome is Outcome.MIGRATED
    for step in ("backups", "upload-target-fileset", "verify-target-fileset", "write-target-package"):
        assert observed[step] == {"old_package": True, "old_fileset": True, "old_profile": True}, step
    assert observed["rewrite-profiles"] == {"old_package": True, "old_fileset": True, "old_profile": True}
    assert observed["delete-old-fileset"] == {"old_package": True, "old_fileset": True, "old_profile": False}
    assert observed["delete-old-package"] == {"old_package": True, "old_fileset": False, "old_profile": False}
    assert observed["final-verify"] == {"old_package": False, "old_fileset": False, "old_profile": False}


def test_an_early_failure_never_has_to_restore_the_old_fileset(tmp_path: Path) -> None:
    """Nothing before the deletions touches the old Fileset, so it needs no restore.

    Restoring it is made impossible here, so a failure that still exits with the
    old state authoritative proves the old Fileset was never deleted.
    """
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])
    filesets.fail_upload.add(LEGACY_PACKAGE)

    def fault(step: str) -> None:
        if step == "write-target-package":
            raise RuntimeError("injected failure at write-target-package")

    with pytest.raises(MigrationError) as raised:
        migrate(request_for(tmp_path), filesets, on_step=fault)

    assert not isinstance(raised.value, RecoveryRequired)
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote


def test_a_lossy_target_upload_is_caught_and_the_old_state_is_restored(tmp_path: Path) -> None:
    """The list API has no checksum, so a short upload only shows up on download."""
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    filesets.drop_on_upload[TARGET_PACKAGE] = {"data/logo.bin"}
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])

    with pytest.raises(MigrationError, match="verify-target-fileset"):
        migrate(request_for(tmp_path), filesets)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote
    assert (WORKSPACE, TARGET_PACKAGE) not in filesets.trees
    assert not (agents_root / TARGET_PACKAGE).exists()


def test_a_pre_existing_equal_target_survives_a_failed_transaction(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    make_target_package(agents_root, filesets)
    target_before = build_manifest(agents_root / TARGET_PACKAGE)
    remote_before = dict(filesets.trees[(WORKSPACE, TARGET_PACKAGE)])

    def fault(step: str) -> None:
        if step == "delete-old-fileset":
            raise RuntimeError("injected failure at delete-old-fileset")

    with pytest.raises(MigrationError):
        migrate(request_for(tmp_path), filesets, on_step=fault)

    assert build_manifest(agents_root / TARGET_PACKAGE) == target_before
    assert filesets.trees[(WORKSPACE, TARGET_PACKAGE)] == remote_before
    assert (agents_root / LEGACY_PACKAGE).is_dir()


def test_a_failure_between_the_two_deletions_restores_both_legacy_copies(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)
    old_remote = dict(filesets.trees[(WORKSPACE, LEGACY_PACKAGE)])

    def fault(step: str) -> None:
        if step == "delete-old-package":
            raise RuntimeError("injected failure at delete-old-package")

    with pytest.raises(MigrationError):
        migrate(request_for(tmp_path), filesets, on_step=fault)

    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert filesets.trees[(WORKSPACE, LEGACY_PACKAGE)] == old_remote


def test_a_failed_compensation_keeps_the_journal_and_reports_recovery_required(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    filesets.fail_upload.add(LEGACY_PACKAGE)

    def fault(step: str) -> None:
        if step == "delete-old-package":
            raise RuntimeError("injected failure at delete-old-package")

    with pytest.raises(RecoveryRequired, match="recovery-required"):
        migrate(request_for(tmp_path), filesets, on_step=fault)

    assert (journal_dir(WORKSPACE, AGENT) / "journal.json").is_file()


def test_a_second_apply_recovers_before_starting_new_work(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    filesets.seed(LEGACY_PACKAGE, as_fileset_tree(legacy_package_files()))
    filesets.fail_upload.add(LEGACY_PACKAGE)
    old_manifest = build_manifest(agents_root / LEGACY_PACKAGE)

    def fault(step: str) -> None:
        if step == "delete-old-package":
            raise RuntimeError("injected failure at delete-old-package")

    with pytest.raises(RecoveryRequired):
        migrate(request_for(tmp_path), filesets, on_step=fault)

    filesets.fail_upload.clear()
    report = migrate(request_for(tmp_path), filesets)

    assert report.outcome is Outcome.RECOVERED
    assert build_manifest(agents_root / LEGACY_PACKAGE) == old_manifest
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_a_journal_whose_target_is_committed_finishes_cleanup(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    make_local_package(agents_root)
    filesets = FakeFilesets()
    profile = write_profile(tmp_path / "optimizer.yaml", {"agent_spec": LEGACY_CONTRACT_FILENAME})

    def fault(step: str) -> None:
        if step == "final-verify":
            raise KeyboardInterrupt("process killed after both deletions")

    with pytest.raises(KeyboardInterrupt):
        migrate(request_for(tmp_path, profiles=(profile,)), filesets, on_step=fault)

    assert (journal_dir(WORKSPACE, AGENT) / "journal.json").is_file()

    report = migrate(request_for(tmp_path, profiles=(profile,)), filesets)

    assert report.outcome is Outcome.RECOVERED
    assert_target_package_is_complete(agents_root, filesets)
    assert not (journal_dir(WORKSPACE, AGENT) / "journal.json").exists()


def test_lock_contention_stops_before_any_mutation(tmp_path: Path) -> None:
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
    assert filesets.uploads == []
    assert not (agents_root / TARGET_PACKAGE).exists()


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
