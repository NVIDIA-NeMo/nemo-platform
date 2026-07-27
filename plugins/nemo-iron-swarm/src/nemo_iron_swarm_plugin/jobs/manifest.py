# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the on-host ``iron-swarm.yaml`` the war-game runs against.

Materializes a saved manifest (agent- or project-sourced) onto disk, applies the run's overrides
(attacker intensity, defender selection, port), and seeds the frozen validate-only baseline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from nemo_iron_swarm_plugin.agent_resolver import resolve_agent_to_manifest
from nemo_iron_swarm_plugin.cli.client import base_url
from nemo_iron_swarm_plugin.entities import IRON_SWARM_MANIFEST_TYPE
from nemo_iron_swarm_plugin.filesets import download_and_extract_project
from nemo_iron_swarm_plugin.jobs.errors import CATEGORY_FILESET, CATEGORY_MANIFEST, IronSwarmRunError
from nemo_platform_plugin.job_context import JobContext

logger = logging.getLogger(__name__)


# Attacker effort presets → garak knobs written into the manifest's top-level `garak:` block.
# "standard" is omitted so iron-swarm's own defaults apply.
INTENSITY_GARAK: dict[str, dict[str, int]] = {
    "light": {"generations": 1, "max_attempts_per_tool": 1},
    "thorough": {"generations": 5, "max_attempts_per_tool": 10},
}

# Defender override entries mirroring iron_swarm.manifest._default_defenders (name + implementation +
# capabilities — iron-swarm's SessionConfig validator requires a non-empty `capabilities`). The entry's
# `config` is unused by the defense stage (the callable gets only its DefenderInput, and the victim policy
# comes from the sandbox), so it's omitted. Selecting a subset replaces the default defender list via the
# manifest's `overrides.defenders` (iron-swarm merges overrides with lists replacing).
DEFENDER_ENTRIES: dict[str, dict[str, Any]] = {
    "openshell": {
        "name": "openshell-policy-defender",
        "implementation": "iron_swarm.agents.defenders.openshell_defender.openshell_defender_agent:run",
        "timeout_seconds": 300,
        "capabilities": (
            "Mitigates attacks that exploit Linux kernel security controls: network egress, filesystem "
            "read/write access, process identity (UID/GID), seccomp syscall filtering, and Landlock path "
            "restrictions. Generates and repairs OpenShell policy YAML patches."
        ),
    },
    "guardrails": {
        "name": "defender-guardrails",
        "implementation": "iron_swarm.agents.defenders.guardrails_defender_v2.guardrails_defender_agent:run",
        "timeout_seconds": 300,
        "capabilities": (
            "Mitigates prompt injection, unsafe tool invocations, sensitive content disclosure, "
            "reconnaissance commands, and untrusted content handling through LLM-generated guardrail rules."
        ),
    },
}


def _agent_model_override(data: dict[str, Any]) -> str | None:
    """The user's chosen victim ("agent" group) model, if any — used to rewrite the victim's IGW LLMs."""
    agent = (data.get("models") or {}).get("agent")
    model = agent.get("model") if isinstance(agent, dict) else None
    return str(model) if model else None


def _apply_manifest_overrides(manifest: dict[str, Any], data: dict[str, Any]) -> None:
    """Re-apply the manifest's persisted war-game overrides (attacker intensity + defender selection).

    The run rebuilds the thin manifest from the agent ref, so these choices — like the victim port —
    must be re-injected here, as iron-swarm's native top-level ``garak:`` block and ``overrides.defenders``
    list. An empty defender selection leaves iron-swarm's defaults untouched.
    """
    garak = INTENSITY_GARAK.get(str(data.get("attack_intensity") or "standard"))
    if garak:
        manifest["garak"] = garak
    # Apply an explicit victim port only when set (stored on the manifest or a per-run override); otherwise
    # leave the port the agent resolver derived from the running deployment.
    if data.get("port"):
        manifest.setdefault("agent", {})["port"] = int(data["port"])
    enabled = [key for key in (data.get("defenders") or []) if key in DEFENDER_ENTRIES]
    if not enabled:
        return
    # Guardrails only applies when the agent has a workflow (iron-swarm gates it the same way).
    has_workflow = bool(manifest.get("agent", {}).get("workflow"))
    entries = [DEFENDER_ENTRIES[key] for key in enabled if key != "guardrails" or has_workflow]
    if entries:
        manifest.setdefault("overrides", {})["defenders"] = entries


def _materialize_manifest(
    sdk: Any, manifest_id: str, ctx: JobContext, config_overrides: dict[str, Any] | None = None
) -> str:
    """Materialize a saved manifest into an on-host ``iron-swarm.yaml``; return its path.

    Fetches the ``IronSwarmManifest`` record and dispatches on its source: ``agent`` re-resolves from
    the stored agent ref via :func:`resolve_agent_to_manifest`; ``project`` re-downloads the uploaded
    bundle and repoints the stored manifest at it. ``sdk`` is the platform SDK (submitted jobs only).

    ``config_overrides`` (per-run port/defenders/attack_intensity from the launch dialog) is overlaid
    onto the stored config so the run can deviate from the manifest without persisting the change.
    """
    if sdk is None:
        raise IronSwarmRunError(
            CATEGORY_MANIFEST, "running a saved manifest requires the platform SDK (submit the job, don't run locally)."
        )
    record = sdk.entities.get_entity_by_name(
        name=manifest_id, entity_type=IRON_SWARM_MANIFEST_TYPE, workspace=ctx.workspace
    )
    data = {**(getattr(record, "data", {}) or {}), **(config_overrides or {})}
    manifest_dir = ctx.storage.persistent
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if (data.get("source_type") or "agent") == "project":
        manifest = _materialize_project_manifest(sdk, manifest_id, data, manifest_dir)
    else:
        manifest = _materialize_agent_manifest(sdk, manifest_id, data, ctx, manifest_dir)
    manifest_path = manifest_dir / "iron-swarm.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return str(manifest_path)


def _materialize_agent_manifest(
    sdk: Any, manifest_id: str, data: dict[str, Any], ctx: JobContext, manifest_dir: Path
) -> dict[str, Any]:
    """Re-resolve an agent-source manifest from its stored agent ref (regenerating the scaffold)."""
    agent_ref = data.get("agent")
    if not agent_ref:
        raise IronSwarmRunError(
            CATEGORY_MANIFEST, f"manifest {manifest_id!r} has no agent reference to materialize from."
        )
    resolved = resolve_agent_to_manifest(
        agent_ref,
        sdk=sdk,
        base_url=base_url(),
        default_workspace=ctx.workspace,
        manifest_dir=manifest_dir,
        model_override=_agent_model_override(data),
    )
    _apply_manifest_overrides(resolved.manifest, data)
    for warning in resolved.warnings:
        logger.warning("manifest %s: %s", manifest_id, warning)
    return resolved.manifest


def _materialize_project_manifest(
    sdk: Any, manifest_id: str, data: dict[str, Any], manifest_dir: Path
) -> dict[str, Any]:
    """Re-download the uploaded project bundle and repoint the stored manifest's ``project_dir`` at it."""
    fileset = data.get("project_fileset")
    manifest_yaml = data.get("manifest_yaml")
    if not fileset or not manifest_yaml:
        raise IronSwarmRunError(
            CATEGORY_MANIFEST, f"project manifest {manifest_id!r} is missing its project_fileset or manifest_yaml."
        )
    try:
        project_dir = download_and_extract_project(sdk, fileset, manifest_dir)
    except IronSwarmRunError:
        raise
    except Exception as exc:  # a fileset download/extract failure is a distinct, actionable class
        raise IronSwarmRunError(
            CATEGORY_FILESET, f"could not download or unpack the project bundle for manifest {manifest_id!r}: {exc}"
        ) from exc
    manifest = yaml.safe_load(manifest_yaml) or {}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("agent"), dict):
        raise IronSwarmRunError(CATEGORY_MANIFEST, f"project manifest {manifest_id!r} has malformed manifest_yaml.")
    manifest["agent"]["project_dir"] = str(project_dir)
    # The bundle's own .env only carries what the project shipped; the victim's secrets (incl. operator-
    # provided ones like a host-backend URL) are materialized next to the manifest. Point secrets_file at
    # that absolute path so iron-swarm's credential provider reads them (a relative ".env" would resolve
    # against the task cwd, where no dotenv exists, and silently deliver nothing).
    manifest["agent"]["secrets_file"] = str((manifest_dir / ".env").resolve())
    _apply_manifest_overrides(manifest, data)
    return manifest


def _seed_validation_manifest(
    manifest_path: str, defense_workflow: str | None, defense_policy: str | None, ctx: JobContext
) -> None:
    """Rewrite a materialized manifest for a frozen validate-only run: zero defenders + composed baseline.

    Seeds the user-chosen composed workflow as the victim's baseline workflow (overwriting the materialized
    scaffold) and, when a policy was chosen, points the victim at the composed OpenShell policy. Forces
    ``overrides.defenders: []`` so iron-swarm runs no defender agents — it deploys this fixed baseline and only
    replays + scores (see the frozen-validation design). Attacks/benign come from ``--replay`` + the suite.
    """
    manifest_dir = ctx.storage.persistent
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    agent = data.get("agent", {})
    if defense_workflow and agent.get("project_dir") and agent.get("workflow"):
        # project_dir may be relative (agent source) or absolute (project source); `/` handles both.
        workflow_file = manifest_dir / agent["project_dir"] / agent["workflow"]
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(defense_workflow, encoding="utf-8")
    overrides = data.setdefault("overrides", {})
    overrides["defenders"] = []  # zero defenders: deploy the frozen baseline, generate nothing
    if defense_policy:
        policy_file = manifest_dir / "composed-policy.yaml"
        policy_file.write_text(defense_policy, encoding="utf-8")
        overrides.setdefault("victim_control", {}).setdefault("config", {})["policy_path"] = str(policy_file)
        overrides.setdefault("storage", {})["victim_policy_path"] = str(policy_file)
    Path(manifest_path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _manifest_facts(manifest_path: str) -> tuple[str, int]:
    """Best-effort read of (agent_name, port) from the manifest for the run record."""
    try:
        data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
        agent = data.get("agent", {}) if isinstance(data, dict) else {}
        return str(agent.get("name", "")), int(agent.get("port", 0) or 0)
    except (OSError, ValueError, yaml.YAMLError):
        return "", 0
