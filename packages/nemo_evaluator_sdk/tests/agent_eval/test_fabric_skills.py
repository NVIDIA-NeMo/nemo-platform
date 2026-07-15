# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for agent-skill injection (pure; no nemo_fabric native stack required)."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.skills import (
    CODEX_SKILLS_DIR,
    SKILL_MODE_CODEX_SKILLS_DIR,
    SKILL_MODE_NATIVE,
    SKILL_PROFILE_NAME,
    AgentSkill,
    SkillInjectionError,
    install_skill,
    native_skills_route,
    resolve_skill_mode,
)


def _plan(*, native: bool | None) -> dict[str, object]:
    """Build a ``RunPlan.capability_plan``-shaped mapping. ``native=None`` means no skills route at all."""
    if native is None:
        return {"routes": []}
    return {"routes": [{"kind": "skills", "target": "harness_native" if native else "unsupported"}]}


_SKILL_MD = "---\nname: code-review\ndescription: Review code thoroughly.\n---\n\nBe thorough."


def _make_bundle(base: Path, name: str = "code-review", extra: dict[str, str] | None = None) -> Path:
    root = base / name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    for rel, content in (extra or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def test_from_directory_defaults_name_from_basename(tmp_path: Path) -> None:
    skill = AgentSkill.from_directory(_make_bundle(tmp_path))
    assert skill.name == "code-review"
    assert skill.directory == (tmp_path / "code-review").resolve()


def test_from_directory_requires_skill_md(tmp_path: Path) -> None:
    src = tmp_path / "no-skill"
    src.mkdir()
    (src / "notes.md").write_text("hi", encoding="utf-8")
    with pytest.raises(SkillInjectionError):
        AgentSkill.from_directory(src)


@pytest.mark.parametrize("bad", ["Code-Review", "-pdf", "pdf-", "pdf--processing", "has space", ""])
def test_invalid_names_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        AgentSkill(name=bad, directory=Path("/skills/x"))


@pytest.mark.parametrize(
    ("capability_plan", "expected"),
    [
        ({"routes": [{"kind": "skills", "target": "harness_native"}]}, True),
        ({"routes": [{"kind": "skills", "target": "unsupported"}]}, False),
        ({"routes": [{"kind": "tools", "target": "harness_native"}]}, False),  # non-skills route ignored
        ({"routes": []}, False),
        ({}, False),  # no routes key
        ({"routes": "not-a-list"}, False),  # defensive: malformed shape
    ],
)
def test_native_skills_route(capability_plan: dict[str, object], expected: bool) -> None:
    assert native_skills_route(capability_plan) is expected


@pytest.mark.parametrize(
    ("capability_plan", "harness", "expected"),
    [
        # Native routing wins regardless of harness name (e.g. Hermes, or an end-user adapter).
        (_plan(native=True), "hermes", SKILL_MODE_NATIVE),
        (_plan(native=True), "acme-custom", SKILL_MODE_NATIVE),
        # Not native, but a codex harness -> self-discovered .agents/skills dir.
        (_plan(native=False), "codex", SKILL_MODE_CODEX_SKILLS_DIR),
        (_plan(native=None), "codex", SKILL_MODE_CODEX_SKILLS_DIR),
        (_plan(native=False), "CODEX", SKILL_MODE_CODEX_SKILLS_DIR),  # case-insensitive
        # Neither native nor codex -> unsupported (runtime fails fast).
        (_plan(native=False), "hermes", None),
        (_plan(native=None), "some-other", None),
    ],
)
def test_resolve_skill_mode(capability_plan: dict[str, object], harness: str, expected: str | None) -> None:
    assert resolve_skill_mode(capability_plan=capability_plan, harness=harness) == expected


def test_install_native_stages_named_dir_and_overlay(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    stage = tmp_path / "stage"
    workspace.mkdir()

    installation = install_skill(
        skill=AgentSkill.from_directory(_make_bundle(tmp_path / "src")),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=workspace,
        skill_stage_dir=stage,
    )

    # Bundle is staged under an isolated <name>/ dir (spec: name matches dir), not the agent workspace.
    skill_root = stage / "code-review"
    assert (skill_root / "SKILL.md").is_file()
    assert not (workspace / "SKILL.md").exists()
    assert not (workspace / ".agents").exists()

    overlay = installation.profiles[0]
    assert overlay["name"] == SKILL_PROFILE_NAME
    assert overlay["skills"] == {"paths": [str(skill_root)]}

    prov = installation.provenance
    assert prov["name"] == "code-review"
    assert prov["mode"] == SKILL_MODE_NATIVE
    assert prov["location"] == str(skill_root)
    assert isinstance(prov["hash"], str) and prov["hash"]


def test_install_native_copies_directory_tree(tmp_path: Path) -> None:
    src = _make_bundle(tmp_path / "src", extra={"references/ref.md": "material", "scripts/run.py": "print()"})
    stage = tmp_path / "stage"

    install_skill(
        skill=AgentSkill.from_directory(src),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "workspace",
        skill_stage_dir=stage,
    )

    base = stage / "code-review"
    assert (base / "SKILL.md").is_file()
    assert (base / "references" / "ref.md").read_text(encoding="utf-8") == "material"
    assert (base / "scripts" / "run.py").read_text(encoding="utf-8") == "print()"


def test_install_codex_places_under_agents_skills(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    installation = install_skill(
        skill=AgentSkill.from_directory(_make_bundle(tmp_path / "src")),
        adapter_id="nvidia.fabric.codex.cli",
        mode=SKILL_MODE_CODEX_SKILLS_DIR,
        workspace_dir=workspace,
        skill_stage_dir=tmp_path / "stage",
    )

    # Codex discovers agentskills bundles from .agents/skills/ in its working directory.
    skill_md = workspace / ".agents" / "skills" / "code-review" / "SKILL.md"
    assert "Be thorough." in skill_md.read_text(encoding="utf-8")
    # No profile overlay: placement in the workspace is the delivery mechanism.
    assert installation.profiles == []
    assert installation.provenance["mode"] == SKILL_MODE_CODEX_SKILLS_DIR
    assert installation.provenance["location"] == f"{CODEX_SKILLS_DIR}/code-review"


def test_codex_bundle_does_not_collide_with_workspace_root(tmp_path: Path) -> None:
    # A task-seeded workspace file at the root is untouched: the skill lives under .agents/skills/.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "data.csv").write_text("task input", encoding="utf-8")
    src = _make_bundle(tmp_path / "src", name="collide", extra={"data.csv": "skill payload"})

    install_skill(
        skill=AgentSkill.from_directory(src),
        adapter_id="nvidia.fabric.codex.cli",
        mode=SKILL_MODE_CODEX_SKILLS_DIR,
        workspace_dir=workspace,
        skill_stage_dir=tmp_path / "stage",
    )

    assert (workspace / "data.csv").read_text(encoding="utf-8") == "task input"
    assert (workspace / ".agents" / "skills" / "collide" / "data.csv").read_text(encoding="utf-8") == "skill payload"


def test_install_native_preserves_existing_skill_paths(tmp_path: Path) -> None:
    # Fabric applies profile skills.paths last-wins, so the overlay must carry the pre-existing paths
    # (order-preserved) alongside the evaluated skill, or the treated arm would drop them.
    installation = install_skill(
        skill=AgentSkill.from_directory(_make_bundle(tmp_path / "src")),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "workspace",
        skill_stage_dir=tmp_path / "stage",
        existing_skill_paths=["/pre/a", "/pre/b", "/pre/a"],  # duplicate is collapsed
    )

    paths = installation.profiles[0]["skills"]["paths"]
    assert paths[:2] == ["/pre/a", "/pre/b"]
    assert paths[-1] == str(tmp_path / "stage" / "code-review")


def test_install_native_recreates_stale_stage(tmp_path: Path) -> None:
    # Re-staging into an existing stage (reused run id) must yield an *exact* copy of the source — a file
    # since removed from the bundle must not survive.
    stage = tmp_path / "stage"
    install_skill(
        skill=AgentSkill.from_directory(_make_bundle(tmp_path / "v1", extra={"old.md": "stale"})),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "workspace",
        skill_stage_dir=stage,
    )
    assert (stage / "code-review" / "old.md").exists()

    install_skill(
        skill=AgentSkill.from_directory(_make_bundle(tmp_path / "v2")),  # no old.md
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "workspace",
        skill_stage_dir=stage,
    )
    assert (stage / "code-review" / "SKILL.md").is_file()
    assert not (stage / "code-review" / "old.md").exists()  # stale file recreated away


def test_install_codex_rejects_reserved_path_collision(tmp_path: Path) -> None:
    # A task seed occupying the reserved Codex skill path must not be silently clobbered/merged.
    workspace = tmp_path / "workspace"
    reserved = workspace / CODEX_SKILLS_DIR / "code-review"
    reserved.mkdir(parents=True)
    (reserved / "task_seed.txt").write_text("task file at the reserved path", encoding="utf-8")

    with pytest.raises(SkillInjectionError, match="reserved path"):
        install_skill(
            skill=AgentSkill.from_directory(_make_bundle(tmp_path / "src")),
            adapter_id="nvidia.fabric.codex.cli",
            mode=SKILL_MODE_CODEX_SKILLS_DIR,
            workspace_dir=workspace,
            skill_stage_dir=tmp_path / "stage",
        )


def test_hash_is_content_sensitive(tmp_path: Path) -> None:
    one = tmp_path / "one" / "code-review"
    two = tmp_path / "two" / "code-review"
    one.mkdir(parents=True)
    two.mkdir(parents=True)
    (one / "SKILL.md").write_text("one", encoding="utf-8")
    (two / "SKILL.md").write_text("two", encoding="utf-8")

    a = install_skill(
        skill=AgentSkill.from_directory(one),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "wa",
        skill_stage_dir=tmp_path / "sa",
    )
    b = install_skill(
        skill=AgentSkill.from_directory(two),
        adapter_id="nvidia.fabric.hermes.sdk",
        mode=SKILL_MODE_NATIVE,
        workspace_dir=tmp_path / "wb",
        skill_stage_dir=tmp_path / "sb",
    )
    assert a.provenance["hash"] != b.provenance["hash"]
