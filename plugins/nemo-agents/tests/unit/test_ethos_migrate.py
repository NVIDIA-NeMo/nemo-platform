# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the Ethos additive migration and cleanup."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from nemo_agents_plugin.cli import AgentsCLI
from nemo_agents_plugin.ethos_migrate import MigrationError, MigrationRequest, run_migration
from typer.testing import CliRunner

AGENT = "acme-bot"
OLD = f"{AGENT}-spec"
NEW = f"{AGENT}-ethos"


def contract() -> str:
    sections = (
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
    body = "\n".join(f"## {section}\n\ncontent\n" for section in sections)
    return (
        "---\nname: acme-bot\ncreated_timestamp: 2026-08-19T12:00:00Z\nauthor: tester\n---\n\n"
        "# Agent Spec: acme-bot\n\n`AGENT-SPEC.md` is written by `nemo-spec`.\n\n" + body
    )


def tree(path: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


@dataclass
class Filesets:
    trees: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    def retrieve(self, name: str, *, workspace: str) -> object:
        if (workspace, name) not in self.trees:
            from nemo_platform import NotFoundError

            raise NotFoundError(
                response=httpx.Response(404, request=httpx.Request("GET", "http://test")),
                body=None,
                message="not found",
            )
        return object()

    def create(self, *, name: str, workspace: str) -> None:
        if (workspace, name) in self.trees:
            from nemo_platform import ConflictError

            raise ConflictError(
                response=httpx.Response(409, request=httpx.Request("POST", "http://test")),
                body=None,
                message="exists",
            )
        self.trees[(workspace, name)] = {}

    def delete(self, name: str, *, workspace: str) -> None:
        self.deleted.append(name)
        self.trees.pop((workspace, name), None)


@dataclass
class Files:
    filesets: Filesets = field(default_factory=Filesets)
    uploads: int = 0

    def download(self, *, local_path: str, fileset: str, workspace: str) -> None:
        root = Path(local_path)
        for name, content in self.filesets.trees[(workspace, fileset)].items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    def upload(self, *, local_path: str, fileset: str, workspace: str, fileset_auto_create: bool) -> None:
        assert not fileset_auto_create
        self.uploads += 1
        root = Path(local_path)
        self.filesets.trees[(workspace, fileset)].update(
            {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        )


@dataclass
class SDK:
    files: Files = field(default_factory=Files)


def request(
    root: Path,
    *,
    profiles: tuple[Path, ...] = (),
    dry_run: bool = False,
    cleanup: bool = False,
) -> MigrationRequest:
    return MigrationRequest(
        agent=AGENT,
        agents_root=root,
        start_dir=root,
        profiles=profiles,
        dry_run=dry_run,
        cleanup=cleanup,
    )


def remote(sdk: SDK, name: str, files: dict[str, str]) -> None:
    sdk.files.filesets.trees[("default", name)] = {key: value.encode() for key, value in files.items()}


def legacy_files() -> dict[str, str]:
    return {"AGENT-SPEC.md": contract(), "agent.yaml": "name: acme-bot\n"}


def external_profile() -> str:
    return f"agent_spec: {OLD}/AGENT-SPEC.md\nother: keep\n"


def package_profile() -> str:
    return "agent_spec: AGENT-SPEC.md\nother: keep\n"


def test_cli_registers_cleanup_and_removes_experiment_dir() -> None:
    result = CliRunner().invoke(AgentsCLI().get_cli(), ["ethos", "migrate", "--help"])

    assert result.exit_code == 0
    assert "--cleanup" in result.stdout
    assert "--experiment-dir" not in result.stdout


@pytest.mark.parametrize("name", ("", ".", "..", "../escape", "a/b"))
def test_rejects_unsafe_agent_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(MigrationError):
        run_migration(MigrationRequest(agent=name, agents_root=tmp_path), sdk=SDK())


def test_rejects_a_symlinked_legacy_package(tmp_path: Path) -> None:
    package = tmp_path / OLD
    source = tmp_path / "source"
    source.mkdir()
    tree(source, legacy_files())
    package.symlink_to(source, target_is_directory=True)

    with pytest.raises(MigrationError, match="symlink"):
        run_migration(request(tmp_path), sdk=SDK())


def test_rejects_a_dangling_legacy_package_symlink(tmp_path: Path) -> None:
    (tmp_path / OLD).symlink_to(tmp_path / "missing-package", target_is_directory=True)

    with pytest.raises(MigrationError, match="symlink"):
        run_migration(request(tmp_path), sdk=SDK())


def test_rejects_a_file_as_a_package_root(tmp_path: Path) -> None:
    (tmp_path / OLD).write_text("not a package\n")

    with pytest.raises(MigrationError, match="not a directory"):
        run_migration(request(tmp_path), sdk=SDK())


def test_migrates_a_local_package_and_converts_profiles(tmp_path: Path) -> None:
    tree(tmp_path / OLD, {**legacy_files(), "optimizer.yaml": package_profile()})
    external = tmp_path / "optimizer.yaml"
    external.write_text(external_profile())
    sdk = SDK()

    report = run_migration(request(tmp_path, profiles=(external,)), sdk=sdk)

    assert report.outcome == "migrated"
    assert (tmp_path / OLD / "AGENT-SPEC.md").is_file()
    assert (tmp_path / NEW / "ETHOS.md").is_file()
    assert "agent_spec" not in external.read_text()
    assert f"ethos: {NEW}/ETHOS.md" in external.read_text()
    assert "agent_spec" not in (tmp_path / NEW / "optimizer.yaml").read_text()
    assert (("default", NEW)) in sdk.files.filesets.trees


def test_leaves_an_unrelated_external_profile_unchanged(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text("other: keep\n")

    run_migration(request(tmp_path, profiles=(external,)), sdk=SDK())

    assert external.read_text() == "other: keep\n"


@pytest.mark.parametrize(
    "payload",
    (
        "agent_spec:\n",
        "ethos:\n",
        f"ethos: {OLD}/AGENT-SPEC.md\n",
        f"agent_spec: {OLD}/AGENT-SPEC.md\nethos: stale/ETHOS.md\n",
    ),
)
def test_dry_run_rejects_invalid_external_profiles(tmp_path: Path, payload: str) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text(payload)
    sdk = SDK()

    with pytest.raises(MigrationError, match="profile"):
        run_migration(request(tmp_path, profiles=(external,), dry_run=True), sdk=sdk)

    assert not (tmp_path / NEW).exists()
    assert not sdk.files.filesets.trees


def test_dry_run_does_not_change_a_rewriteable_external_profile(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text(external_profile())
    original = external.read_bytes()

    run_migration(request(tmp_path, profiles=(external,), dry_run=True), sdk=SDK())

    assert external.read_bytes() == original


def test_accepts_a_home_relative_ethos_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    tree(home / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text(f"ethos: ~/{NEW}/ETHOS.md\n")

    run_migration(request(home, profiles=(external,)), sdk=SDK())

    assert external.read_text() == f"ethos: ~/{NEW}/ETHOS.md\n"


def test_rejects_a_stale_ethos_profile(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text("ethos: another-agent-ethos/ETHOS.md\n")

    with pytest.raises(MigrationError, match="target"):
        run_migration(request(tmp_path, profiles=(external,)), sdk=SDK())


def test_does_not_overwrite_a_profile_tmp_sibling(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text(external_profile())
    sibling = external.with_suffix(".tmp")
    sibling.write_text("preserve\n")

    run_migration(request(tmp_path, profiles=(external,)), sdk=SDK())

    assert sibling.read_text() == "preserve\n"


def test_migrates_a_fileset_only_source(tmp_path: Path) -> None:
    sdk = SDK()
    remote(sdk, OLD, legacy_files())

    run_migration(request(tmp_path), sdk=sdk)

    assert (tmp_path / NEW / "ETHOS.md").is_file()
    assert "ETHOS.md" in sdk.files.filesets.trees[("default", NEW)]


def test_merges_matching_dual_sources_and_rejects_divergent_files(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    remote(sdk, OLD, {**legacy_files(), "from-remote.txt": "remote"})

    run_migration(request(tmp_path), sdk=sdk)

    assert (tmp_path / NEW / "from-remote.txt").read_text() == "remote"
    tree(tmp_path / "other" / OLD, legacy_files())
    remote(sdk, OLD, {**legacy_files(), "agent.yaml": "different"})
    with pytest.raises(MigrationError, match="disagree"):
        run_migration(request(tmp_path / "other"), sdk=sdk)


@pytest.mark.parametrize("target_files", ({"extra.txt": "x"}, {"agent.yaml": "different"}))
def test_rejects_extra_or_divergent_targets(tmp_path: Path, target_files: dict[str, str]) -> None:
    tree(tmp_path / OLD, legacy_files())
    tree(tmp_path / NEW, target_files)

    with pytest.raises(MigrationError, match="target"):
        run_migration(request(tmp_path), sdk=SDK())


def test_completes_compatible_partial_targets(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    tree(tmp_path / NEW, {"agent.yaml": "name: acme-bot\n"})
    sdk = SDK()
    remote(sdk, NEW, {"agent.yaml": "name: acme-bot\n"})

    run_migration(request(tmp_path), sdk=sdk)

    assert (tmp_path / NEW / "ETHOS.md").is_file()
    assert "ETHOS.md" in sdk.files.filesets.trees[("default", NEW)]


def test_skips_upload_for_a_complete_fileset_target(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    run_migration(request(tmp_path), sdk=sdk)
    uploads = sdk.files.uploads

    run_migration(request(tmp_path), sdk=sdk)

    assert sdk.files.uploads == uploads


@pytest.mark.parametrize("target_files", ({"extra.txt": "x"}, {"agent.yaml": "different"}))
def test_rejects_a_divergent_fileset_target_before_writing_local_target(
    tmp_path: Path, target_files: dict[str, str]
) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    remote(sdk, NEW, target_files)

    with pytest.raises(MigrationError, match="Fileset target differs"):
        run_migration(request(tmp_path), sdk=sdk)

    assert not (tmp_path / NEW).exists()
    assert sdk.files.filesets.trees[("default", NEW)] == {
        name: content.encode() for name, content in target_files.items()
    }


@pytest.mark.parametrize(
    ("local_target", "fileset_target"),
    (
        ({"extra.txt": "x"}, None),
        (None, {"extra.txt": "x"}),
    ),
)
def test_dry_run_rejects_divergent_targets(
    tmp_path: Path, local_target: dict[str, str] | None, fileset_target: dict[str, str] | None
) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    if local_target is not None:
        tree(tmp_path / NEW, local_target)
    if fileset_target is not None:
        remote(sdk, NEW, fileset_target)

    with pytest.raises(MigrationError, match="target differs"):
        run_migration(request(tmp_path, dry_run=True), sdk=sdk)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()

    report = run_migration(request(tmp_path, dry_run=True), sdk=sdk)

    assert report.outcome == "pending"
    assert not (tmp_path / NEW).exists()
    assert not sdk.files.filesets.trees


def test_rejects_invalid_contract_and_legacy_literals(tmp_path: Path) -> None:
    tree(tmp_path / OLD, {**legacy_files(), "readme.md": "agent_spec remains"})

    with pytest.raises(MigrationError, match="legacy"):
        run_migration(request(tmp_path), sdk=SDK())


def test_allows_documented_legacy_substrings(tmp_path: Path) -> None:
    tree(
        tmp_path / OLD,
        {
            **legacy_files(),
            "nemo-agents-spec-v1.txt": "agent-specific behavior\n",
        },
    )

    run_migration(request(tmp_path), sdk=SDK())

    assert (tmp_path / NEW / "nemo-agents-spec-v1.txt").is_file()


def test_rejects_a_descendant_profile_symlink(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "external.yaml"
    external.write_text(external_profile())
    link = tmp_path / OLD / "nested" / "optimizer.yaml"
    link.parent.mkdir()
    link.symlink_to(external)

    with pytest.raises(MigrationError, match="symlink"):
        run_migration(request(tmp_path), sdk=SDK())

    assert "agent_spec" in external.read_text()


def test_cleanup_requires_complete_targets_then_deletes_each_legacy_copy(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    remote(sdk, OLD, legacy_files())

    with pytest.raises(MigrationError, match="complete"):
        run_migration(request(tmp_path, cleanup=True), sdk=sdk)
    run_migration(request(tmp_path), sdk=sdk)
    run_migration(request(tmp_path, cleanup=True), sdk=sdk)

    assert not (tmp_path / OLD).exists()
    assert ("default", OLD) not in sdk.files.filesets.trees


def test_cleanup_blocks_an_unconverted_external_profile(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    external = tmp_path / "optimizer.yaml"
    external.write_text(external_profile())
    sdk = SDK()
    remote(sdk, OLD, legacy_files())
    run_migration(request(tmp_path), sdk=sdk)

    external.write_text(external_profile())
    with pytest.raises(MigrationError, match="converted profile"):
        run_migration(request(tmp_path, profiles=(external,), cleanup=True), sdk=sdk)

    assert (tmp_path / OLD).exists()
    assert ("default", OLD) in sdk.files.filesets.trees


def test_cleanup_dry_run_preserves_legacy_artifacts(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    remote(sdk, OLD, legacy_files())
    run_migration(request(tmp_path), sdk=sdk)

    report = run_migration(request(tmp_path, cleanup=True, dry_run=True), sdk=sdk)

    assert report.outcome == "pending"
    assert (tmp_path / OLD).exists()
    assert ("default", OLD) in sdk.files.filesets.trees


def test_cleanup_rejects_a_dangling_legacy_package_symlink(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    sdk = SDK()
    run_migration(request(tmp_path), sdk=sdk)
    shutil.rmtree(tmp_path / OLD)
    (tmp_path / OLD).symlink_to(tmp_path / "missing-package", target_is_directory=True)

    with pytest.raises(MigrationError, match="symlink"):
        run_migration(request(tmp_path, cleanup=True), sdk=sdk)

    assert (tmp_path / OLD).is_symlink()


def test_cleanup_rejects_an_invalid_target_contract(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    tree(tmp_path / NEW, {"ETHOS.md": "not a contract\n"})
    sdk = SDK()
    remote(sdk, OLD, legacy_files())
    remote(sdk, NEW, {"ETHOS.md": "not a contract\n"})

    with pytest.raises(MigrationError, match="invalid"):
        run_migration(request(tmp_path, cleanup=True), sdk=sdk)


def test_cleanup_reruns_after_the_local_delete(tmp_path: Path) -> None:
    tree(tmp_path / OLD, legacy_files())
    tree(
        tmp_path / NEW,
        {
            "ETHOS.md": contract()
            .replace("Agent Spec:", "Ethos:")
            .replace("AGENT-SPEC.md", "ETHOS.md")
            .replace("nemo-spec", "nemo-ethos"),
            "agent.yaml": "name: acme-bot\n",
        },
    )
    sdk = SDK()
    remote(sdk, OLD, legacy_files())
    remote(sdk, NEW, {"ETHOS.md": (tmp_path / NEW / "ETHOS.md").read_text(), "agent.yaml": "name: acme-bot\n"})

    original_delete = sdk.files.filesets.delete

    def fail_old(name: str, *, workspace: str) -> None:
        if name == OLD:
            raise OSError("interrupted")
        original_delete(name, workspace=workspace)

    with patch.object(sdk.files.filesets, "delete", fail_old), pytest.raises(OSError):
        run_migration(request(tmp_path, cleanup=True), sdk=sdk)
    assert not (tmp_path / OLD).exists()
    run_migration(request(tmp_path, cleanup=True), sdk=sdk)
    assert ("default", OLD) not in sdk.files.filesets.trees
