# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity definitions for the Iron Swarm plugin — stored in the NeMo Platform entity store.

A :class:`IronSwarmRun` records one war-game run (agent targeted, victim port, manifest, outcome); a
:class:`IronSwarmManifest` is a named, reusable war-game target scaffolded from a deployed agent or an
uploaded NAT project. ``name``/``workspace``/``created_at``/``id`` are inherited from the base and
managed by the store; only domain fields are declared here. The ``IRON_SWARM_*_TYPE`` constants are
the canonical entity-type strings used at every call site.
"""

from __future__ import annotations

from typing import Literal

from nemo_iron_swarm_plugin.model_config import WarGameModels
from nemo_platform_plugin.entity import NemoEntity
from pydantic import Field

IRON_SWARM_RUN_TYPE = "iron_swarm_run"
IRON_SWARM_MANIFEST_TYPE = "iron_swarm_manifest"

RunStatus = Literal["running", "completed", "failed"]
ManifestSource = Literal["agent", "project"]


class IronSwarmRun(NemoEntity, entity_type=IRON_SWARM_RUN_TYPE):
    """A record of one Iron Swarm war-game run."""

    agent: str = Field(default="", description="Targeted agent reference (workspace/name).")
    job_id: str = Field(default="", description="Platform job that drove this run (for live status/HITL).")
    port: int = Field(default=0, description="Victim port the war-game attacked.")
    manifest: str = Field(default="", description="Path to the iron-swarm.yaml manifest used.")
    manifest_id: str = Field(default="", description="Manifest this run belongs to (scopes 'replay last run').")
    status: RunStatus = Field(default="failed", description="Final run status.")
    returncode: int = Field(default=-1, description="Exit code from `iron-swarm run`.")
    summary: str = Field(default="", description="Short human-readable outcome summary.")
    error_category: str = Field(
        default="",
        description="Classified failure category when status is 'failed' (e.g. sandbox, missing_credential, "
        "manifest, network); empty for a successful run.",
    )
    error_message: str = Field(default="", description="Operator-facing failure message when the run failed.")
    error_remediation: str = Field(
        default="", description="Suggested next step to resolve the failure; empty for a successful run."
    )
    hitlog_fileset: str = Field(
        default="",
        description="Fileset ref of the garak hitlog this run produced, if any; replay a later run from it.",
    )
    events_fileset: str = Field(
        default="",
        description="Fileset ref of the run's events.jsonl, uploaded at completion for durable history.",
    )
    source_run: str = Field(
        default="",
        description="For a validate-only sanity-check run, the name of the harden run it was launched from; "
        "lets the Harden tab re-attach the scorecard on reload. Empty for normal war-game runs.",
    )


class IronSwarmManifest(NemoEntity, entity_type=IRON_SWARM_MANIFEST_TYPE):
    """A named, reusable war-game target scaffolded via `init` (its ``name`` is the user-defined id).

    Two sources: ``agent`` re-materializes the manifest from a deployed agent ref (no bundle persisted);
    ``project`` war-games an uploaded NAT project — its files are stored as ``project_fileset`` and the
    run re-downloads them so custom-tool agents (unregistrable as config-only agents) can be targeted.
    """

    agent: str = Field(default="", description="Deployed agent reference (workspace/name) this manifest targets.")
    source_type: ManifestSource = Field(default="agent", description="How the manifest was built ('agent'|'project').")
    project_fileset: str = Field(
        default="",
        description="Fileset ref holding the uploaded NAT project bundle (source_type 'project'); the run "
        "re-downloads it to a project_dir before launching the victim.",
    )
    workflow: str = Field(default="", description="Chosen workflow path within the project (project source, display).")
    launch_mode: str = Field(default="", description="Victim launch mode ('workflow'|'byo'; project source).")
    manifest_yaml: str = Field(default="", description="The resolved iron-swarm.yaml content (for display).")
    port: int = Field(default=0, description="Victim port the war-game will target.")
    secrets: list[str] = Field(default_factory=list, description="Secret names the victim agent requires.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal notes from scaffolding.")
    benign_suite: list[dict[str, str]] = Field(
        default_factory=list,
        description="Cached, reviewed benign test suite (tool,payload,label,rationale,persona rows); "
        "generated on the first run and reused/edited thereafter. Empty until generated.",
    )
    benign_interview: list[dict[str, str]] = Field(
        default_factory=list,
        description="Interview Q&A (gap,question,answer rows) captured during the last benign-suite "
        "generation, kept for display. Empty until generated.",
    )
    defenders: list[str] = Field(
        default_factory=list,
        description="Enabled defender keys ('guardrails','openshell'); empty means iron-swarm's defaults "
        "(all applicable). Materialized into the manifest's overrides.defenders at run time.",
    )
    attack_intensity: Literal["light", "standard", "thorough"] = Field(
        default="standard",
        description="Attacker (garak) effort preset, materialized into the manifest's garak block at run time.",
    )
    rounds: int = Field(
        default=1,
        ge=1,
        description="Number of iterative attack/defend/validate hardening rounds; passed to iron-swarm's "
        "`run --rounds` at run time.",
    )
    models: WarGameModels = Field(
        default_factory=WarGameModels,
        description="Stored default model selection (attack/analysis/agent groups); an unset group uses "
        "iron-swarm's built-in default. A run may override these per-launch.",
    )

    @classmethod
    def from_agent_resolution(
        cls,
        *,
        name: str,
        workspace: str,
        agent_ref: str,
        manifest_yaml: str,
        port: int,
        secrets: list[str],
        warnings: list[str],
        models: WarGameModels | None = None,
    ) -> IronSwarmManifest:
        """Build an ``agent``-source manifest entity from a resolved agent scaffold.

        Shared by the CLI ``init`` and the Studio ``POST /manifests`` handler so both persist the same
        shape from :func:`resolve_agent_to_manifest`'s output (the run re-materializes from ``agent_ref``).
        """
        return cls(
            name=name,
            workspace=workspace,
            agent=agent_ref,
            source_type="agent",
            manifest_yaml=manifest_yaml,
            port=port,
            secrets=secrets,
            warnings=warnings,
            models=models or WarGameModels(),
        )
