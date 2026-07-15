# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent-skill injection for the Fabric agent-eval runtimes (PROTOTYPE).

An *agent skill* is a directory following the `agentskills.io <https://agentskills.io/specification>`_
spec: a folder named ``<name>/`` containing a required ``SKILL.md`` (YAML frontmatter with ``name`` +
``description``, then instructions) plus optional ``scripts/`` / ``references/`` / ``assets/``. We make
that bundle available to the harness before it runs a task so an A/B eval can score the same taskset
with and without the skill. The skill is a runtime-level knob: build one runtime with ``skill=None``
and one with ``skill=<AgentSkill>`` over the same tasks, then diff the scores.

An :class:`AgentSkill` points at a local skill directory; staging is an OS-level ``copytree`` (file
contents never pass through Python memory). The plugin resolves a platform fileset to a local
directory and constructs an ``AgentSkill`` from it — the SDK has no fileset concept of its own.

How the skill reaches the harness depends on the selected Fabric adapter, and which mode applies is
decided by *querying Fabric's own capability planner at runtime* (:func:`resolve_skill_mode` over a
``RunPlan.capability_plan``), not a hardcoded adapter list — so it tracks whatever the installed
adapters declare, including end-user adapters we don't ship:

* **Native** (:data:`SKILL_MODE_NATIVE`): the adapter advertises ``accepts: ["skills", ...]`` (the
  Hermes/Claude adapters do), so Fabric's planner routes skills to ``harness_native``. We stage the
  bundle into an isolated ``<name>/`` dir and hand Fabric a ``skills.paths`` profile overlay; the
  adapter loads it (Hermes → harness ``skills.external_dirs``).
* **Codex skills dir** (:data:`SKILL_MODE_CODEX_SKILLS_DIR`): the Fabric ``codex`` adapter only
  ``accepts: ["models"]`` (planner routes skills ``unsupported``), but the Codex CLI itself discovers
  agentskills bundles from ``.agents/skills/`` in its working directory. So we place the bundle at
  ``<workspace>/.agents/skills/<name>/`` and let Codex discover it — same discoverable-skill semantics
  as native (cross-harness A/B is apples-to-apples), no Fabric adapter change needed.

If an adapter neither routes skills natively nor is a Codex harness, :func:`resolve_skill_mode` returns
``None`` and the runtime fails fast rather than silently running a skill-free trial.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Required entry document of an agentskills bundle.
PRIMARY_SKILL_DOC = "SKILL.md"
#: Directory Codex scans (relative to its working dir) for agentskills bundles.
CODEX_SKILLS_DIR = ".agents/skills"
#: Name of the Fabric profile overlay that carries the native ``skills`` config.
SKILL_PROFILE_NAME = "eval_skill"

#: Skill reaches the harness via the native Fabric ``skills`` config (adapter accepts it).
SKILL_MODE_NATIVE = "native"
#: Skill is placed under ``<workspace>/.agents/skills/<name>/`` for Codex to discover.
SKILL_MODE_CODEX_SKILLS_DIR = "codex_skills_dir"

# agentskills.io name rule: 1-64 chars, lowercase alphanumeric + single interior hyphens.
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64

# Fabric capability-planner vocabulary (``RunPlan.capability_plan['routes']`` entries). A ``skills``
# route with target ``harness_native`` means the selected adapter declared native skills support; the
# runtime plans a probe skill path and reads these to decide the injection mode (see resolve_skill_mode).
_SKILLS_ROUTE_KIND = "skills"
_SKILLS_TARGET_NATIVE = "harness_native"
# Fabric harness name of the Codex CLI adapter, which self-discovers ``.agents/skills/`` rather than
# accepting the native ``skills`` config.
_CODEX_HARNESS = "codex"


class SkillInjectionError(ValueError):
    """A skill could not be resolved, staged, or wired into the selected harness.

    Subclasses ``ValueError`` so the runtime's per-task error handling still catches it and fails
    only that task.
    """


class AgentSkill(BaseModel):
    """An agentskills.io bundle (a local directory) to make available to the agent before a task.

    ``name`` must satisfy the agentskills naming rule and is used as the staged bundle's directory name
    (spec: the name matches the directory name). ``directory`` is the local skill directory, which must
    contain a top-level ``SKILL.md``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="agentskills skill name; also the bundle directory name and provenance id.")
    directory: Path = Field(description="Local agentskills bundle directory (a SKILL.md at its root).")

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if len(value) > _MAX_NAME_LEN or not _SKILL_NAME_RE.match(value):
            raise ValueError(
                f"skill name {value!r} must be 1-{_MAX_NAME_LEN} chars, lowercase alphanumeric with "
                "single interior hyphens (agentskills.io naming rule)"
            )
        return value

    @classmethod
    def from_directory(cls, directory: str | Path, *, name: str | None = None) -> AgentSkill:
        """Build a skill from an on-disk agentskills bundle. ``name`` defaults to the directory basename."""
        root = Path(directory).expanduser().resolve()
        if not (root / PRIMARY_SKILL_DOC).is_file():
            raise SkillInjectionError(f"skill directory {str(directory)!r} has no {PRIMARY_SKILL_DOC}")
        return cls(name=name or root.name, directory=root)


class SkillProvenance(TypedDict):
    """Which skill was injected into a trial and how; stamped into trial metadata for the A/B diff.

    A plain (JSON-serializable) dict so it drops straight into trial metadata. ``None`` in that slot
    means the baseline (no skill).
    """

    name: str  #: The skill's agentskills name.
    hash: str  #: sha256 over the staged bundle — attributes a score delta to an exact skill version.
    mode: str  #: How it was injected (:data:`SKILL_MODE_NATIVE` / :data:`SKILL_MODE_CODEX_SKILLS_DIR`).
    adapter_id: str  #: The harness adapter the skill was wired into.
    location: str  #: Where the bundle was staged (absolute for native, workspace-relative for codex).


@dataclass
class SkillInstallation:
    """Result of installing a skill for one task.

    ``profiles`` are Fabric profile-overlay mappings the runtime appends to its profile stack (the
    native branch emits one ``skills`` overlay; the Codex branch emits none because placement in the
    workspace is the delivery mechanism). ``provenance`` is stamped into trial metadata so the A/B
    comparison is auditable.
    """

    profiles: list[dict[str, object]]
    provenance: SkillProvenance


def native_skills_route(capability_plan: Mapping[str, object]) -> bool:
    """Whether Fabric's capability planner routed skills to the harness natively.

    ``capability_plan`` is the ``RunPlan.capability_plan`` mapping from ``Fabric.plan(...)`` planned with
    a skill path attached; its ``routes`` record each capability decision. A ``skills`` route with target
    ``harness_native`` means the selected adapter declares ``accepts: ["skills", ...]`` and Fabric hands
    the bundle to the harness itself. Any other outcome (``unsupported``, or no skills route) is False.
    """
    routes = capability_plan.get("routes")
    if not isinstance(routes, list):
        return False
    return any(
        isinstance(route, Mapping)
        and route.get("kind") == _SKILLS_ROUTE_KIND
        and route.get("target") == _SKILLS_TARGET_NATIVE
        for route in routes
    )


def resolve_skill_mode(*, capability_plan: Mapping[str, object], harness: str) -> str | None:
    """Resolve how a skill would reach the selected harness, or ``None`` if it can't.

    Driven by Fabric's own capability routing (queried at runtime via ``Fabric.plan``) rather than a
    hardcoded adapter list, so it tracks whatever the installed adapters declare — including end-user
    adapters we don't ship:

    * skills route natively (:func:`native_skills_route`) -> :data:`SKILL_MODE_NATIVE`;
    * else a Codex harness (self-discovers ``.agents/skills/``) -> :data:`SKILL_MODE_CODEX_SKILLS_DIR`;
    * else ``None`` -> the runtime fails fast rather than run a skill-free trial labeled "with skill".
    """
    if native_skills_route(capability_plan):
        return SKILL_MODE_NATIVE
    if harness.strip().lower() == _CODEX_HARNESS:
        return SKILL_MODE_CODEX_SKILLS_DIR
    return None


def install_skill(
    *,
    skill: AgentSkill,
    adapter_id: str,
    mode: str,
    workspace_dir: Path,
    skill_stage_dir: Path,
    existing_skill_paths: Sequence[str] = (),
) -> SkillInstallation:
    """Stage ``skill`` as a ``<name>/`` bundle and wire it into the harness per ``mode``.

    Blocking file I/O — call via ``asyncio.to_thread`` from the async runtime. The bundle is always
    namespaced under ``<name>/`` so it never collides with task-seeded workspace-root files; the content
    hash is computed over the staged bytes so provenance tracks the actual skill content.

    ``existing_skill_paths`` are the skill paths the base config/profiles already declare. Fabric applies
    profile ``skills.paths`` last-wins, so the native overlay must re-list them alongside the evaluated
    skill — otherwise the treated arm would silently drop every preconfigured skill and the A/B would
    differ by more than the injected skill.
    """
    if mode == SKILL_MODE_NATIVE:
        skill_root = skill_stage_dir / skill.name
        _stage_bundle(skill.directory, skill_root, reserved=False)
        # Preserve the pre-existing skill paths (order-preserved, de-duplicated) and append the
        # evaluated skill, so the last-wins overlay reproduces the baseline skill set plus this one.
        paths = list(dict.fromkeys([*existing_skill_paths, str(skill_root)]))
        overlay: dict[str, object] = {
            "name": SKILL_PROFILE_NAME,
            "description": "Make the evaluation skill available via the native Fabric skills config.",
            "skills": {"paths": paths},
        }
        return SkillInstallation(
            profiles=[overlay],
            provenance=_provenance(skill, _hash_directory(skill_root), mode, adapter_id, str(skill_root)),
        )

    if mode == SKILL_MODE_CODEX_SKILLS_DIR:
        skill_root = workspace_dir / CODEX_SKILLS_DIR / skill.name
        _stage_bundle(skill.directory, skill_root, reserved=True)
        location = (Path(CODEX_SKILLS_DIR) / skill.name).as_posix()
        return SkillInstallation(
            profiles=[],
            provenance=_provenance(skill, _hash_directory(skill_root), mode, adapter_id, location),
        )

    raise SkillInjectionError(f"unknown skill injection mode {mode!r} for adapter {adapter_id!r}")


def _stage_bundle(directory: Path, skill_root: Path, *, reserved: bool) -> None:
    """Stage the skill ``directory`` as an *exact* copy at ``skill_root`` (the ``<name>/`` bundle dir).

    The staged bundle must reflect exactly the supplied directory, so provenance and behaviour track the
    real content. ``reserved`` picks the collision policy for the destination:

    * ``reserved=False`` — the evaluator-owned native stage dir: recreate it, so a reused run id can't
      leave a file that was since removed from the source bundle surviving in the stage.
    * ``reserved=True`` — the Codex workspace path (``.agents/skills/<name>``): refuse to clobber
      pre-existing content there, since it can only be a task-seeded file colliding with the reserved
      skill path.
    """
    src = directory.expanduser()
    if not (src / PRIMARY_SKILL_DOC).is_file():
        raise SkillInjectionError(f"skill directory {str(directory)!r} has no {PRIMARY_SKILL_DOC}")
    if skill_root.exists():
        if reserved:
            raise SkillInjectionError(
                f"cannot stage skill into reserved path {str(skill_root)!r}: it already exists "
                "(a task-seeded file collides with the injected skill bundle)"
            )
        shutil.rmtree(skill_root)  # evaluator-owned: recreate so the stage is an exact copy
    skill_root.parent.mkdir(parents=True, exist_ok=True)
    # OS-level copy — file contents never pass through Python memory.
    shutil.copytree(src, skill_root)


def _provenance(skill: AgentSkill, skill_hash: str, mode: str, adapter_id: str, location: str) -> SkillProvenance:
    return {
        "name": skill.name,
        "hash": skill_hash,
        "mode": mode,
        "adapter_id": adapter_id,
        "location": location,
    }


def _hash_directory(directory: Path) -> str:
    """Stable sha256 over a directory's file tree (sorted relpath + contents)."""
    digest = hashlib.sha256()
    for path in sorted(path for path in directory.rglob("*") if path.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
