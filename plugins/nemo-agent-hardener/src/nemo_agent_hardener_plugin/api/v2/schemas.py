# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent Hardener plugin API request/query schemas.

The persisted entities are the same shape on the wire as at rest, so the read routes return them
directly. This module holds the list-endpoint query filters (extending ``NemoFilter``,
``extra="forbid"`` so a misspelled key 422s) plus the ``POST /manifests`` init request body.
"""

from __future__ import annotations

from typing import Any, Literal

from nemo_agent_hardener_plugin.model_config import WarGameModels
from nemo_platform_plugin.schema import NemoFilter
from pydantic import BaseModel, Field, model_validator


class RunFilter(NemoFilter):
    """Query filter for ``GET /v2/workspaces/{workspace}/runs``."""

    agent: str | None = Field(
        default=None,
        description="Filter to runs targeting this agent reference (workspace/name).",
    )
    manifest_id: str | None = Field(
        default=None,
        description="Filter to runs launched from this manifest (scopes 'replay last run').",
    )
    status: str | None = Field(
        default=None,
        description="Filter to runs with this status ('running', 'completed', or 'failed').",
    )


class ManifestFilter(NemoFilter):
    """Query filter for ``GET /v2/workspaces/{workspace}/manifests``."""

    agent: str | None = Field(default=None, description="Filter to manifests for this agent reference.")


class ManifestInit(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/manifests`` — scaffold a named manifest.

    Two sources. ``agent`` is a registered platform agent, which the resolver reads and renders.
    ``project`` is an uploaded project bundle — an image whose author owns the Dockerfile, which a
    Fabric ``agent.yaml`` cannot express. The user never writes ``agent-hardener.yaml`` either way: the
    project source derives it and asks only for the fields a project cannot state about itself.
    """

    name: str = Field(description="User-defined manifest id (unique within the workspace).")
    source_type: Literal["agent", "project"] = Field(
        default="agent",
        description="Where the victim comes from: a registered platform agent, or an uploaded project bundle.",
    )
    agent: str | None = Field(
        default=None,
        description="Agent reference (``name`` or ``workspace/name``) to war-game. Required when "
        "``source_type`` is 'agent'.",
    )
    project_fileset: str | None = Field(
        default=None,
        description="Fileset ref (``workspace/name``) of the uploaded project bundle. Required when "
        "``source_type`` is 'project'.",
    )
    dockerfile: str | None = Field(
        default=None,
        description="Dockerfile path relative to the project root. Derived when the project holds exactly one.",
    )
    start_command: str | None = Field(
        default=None,
        description="Command that serves the agent. Derived from the Dockerfile's ENTRYPOINT/CMD when it is "
        "an exec form we can resolve.",
    )
    binaries: list[str] | None = Field(
        default=None,
        description="Glob(s) matching the victim's interpreter, for the sandbox's egress policy. A glob that "
        "matches no process grants nothing while looking like it grants something, so this is confirmed "
        "rather than silently guessed.",
    )
    harness: str | None = Field(
        default=None,
        description="Which harness the agent runs, so the run can say up front whether a guardrail can refuse "
        "a tool call. Not knowable from the project.",
    )
    relay_integration_confirmed: bool = Field(
        default=False,
        description="The author confirms NeMo Relay is attached (middleware + plugin.initialize()). Not "
        "knowable from the project; without Relay the victim emits no telemetry and cannot be scored.",
    )
    port: int | None = Field(default=None, description="Victim port (defaults to 8000).")
    secrets: list[str] | None = Field(
        default=None,
        description="Env-var names the victim requires. Derived from the agent's own declarations "
        "(``models.*.api_key_env``, MCP server env) when omitted.",
    )
    egress: list[str] | None = Field(
        default=None,
        description="Allow-listed egress host[:port] entries the victim may reach (external hosts the agent "
        "calls, e.g. inference-api.nvidia.com). The sandbox is default-deny, so a host missing here has its "
        "traffic dropped mid-run.",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Non-secret environment variables for the victim (agent-hardener's `agent.env`). Stored in "
        "plaintext on the manifest — credentials belong in `secrets`, which names them and "
        "resolves the values from the Secrets store at run time.",
    )
    backends: list[str] | None = Field(
        default=None,
        description="Route-only host backends the agent's tools call, each 'NAME:PORT[,PORT2]' (e.g. "
        "'finance:8086'). Rewrites the agent's localhost:PORT to host.docker.internal:PORT and opens the "
        "sandbox->host route.",
    )
    models: WarGameModels | None = Field(
        default=None,
        description="Stored default model selection (attack/analysis/agent groups); omit to use agent-hardener's "
        "built-in defaults.",
    )

    @model_validator(mode="after")
    def _source_matches_fields(self) -> "ManifestInit":
        """Reject a body whose source and fields disagree, rather than resolving the wrong one.

        Both fields being free-form strings, a request that names an agent *and* a project bundle has no
        obviously-correct reading — and picking one silently would war-game a target the caller did not ask
        for.
        """
        required, forbidden = (
            ("agent", "project_fileset")
            if self.source_type == "agent"
            else (
                "project_fileset",
                "agent",
            )
        )
        if not getattr(self, required):
            raise ValueError(f"source_type '{self.source_type}' requires '{required}'")
        if getattr(self, forbidden):
            raise ValueError(f"source_type '{self.source_type}' does not accept '{forbidden}'")
        return self


class ValidateModelRequest(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/model-config/validate`` — probe a model choice."""

    model: str | None = Field(default=None, description="Model name to verify against the endpoint's model list.")
    base_url: str = Field(description="OpenAI-compatible endpoint to probe (`GET {base_url}/models`).")
    api_key_secret: str | None = Field(
        default=None, description="Secret name holding the provider key; omitted probes without auth."
    )


class ValidateModelResponse(BaseModel):
    """Verdict for a model choice; ``available`` lists what the credentials can reach so the UI offers real options."""

    ok: bool = Field(description="True when the endpoint is reachable, authorized, and serves the model.")
    reason: str = Field(default="", description="'' | 'auth' | 'unreachable' | 'unknown_model'.")
    available: list[str] = Field(default_factory=list, description="Model ids the credentials can reach.")
    detail: str = Field(default="", description="Human-readable diagnostic (status code / transport error).")


class InspectProjectRequest(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/manifests/inspect-project`` — read an uploaded project."""

    project_fileset: str = Field(description="Fileset ref of the uploaded project bundle to inspect.")
    dockerfile: str | None = Field(
        default=None,
        description="Which Dockerfile builds the agent, when the bundle holds more than one.",
    )


class InspectProjectResponse(BaseModel):
    """What the project states about itself, plus what it cannot.

    ``unresolved`` is the contract with the caller: everything else on this model is a usable value, and
    these are the only fields a human still has to supply. It is the difference between a form that asks
    for everything and one that asks for what is genuinely unknowable.
    """

    dockerfile: str = Field(default="", description="Dockerfile path relative to the project root.")
    dockerfiles: list[str] = Field(
        default_factory=list, description="Every Dockerfile found, when the choice is ambiguous."
    )
    start_command: str = Field(default="", description="Derived from the Dockerfile's ENTRYPOINT/CMD.")
    binaries: list[str] = Field(default_factory=list, description="Proposed interpreter globs, for confirmation.")
    port: int = Field(default=8000, description="Derived from EXPOSE / ENV PORT.")
    secrets: list[str] = Field(default_factory=list, description="Secret names derived from .env and ENV.")
    egress: list[str] = Field(default_factory=list, description="Hosts the project's own files name.")
    env: dict[str, str] = Field(default_factory=dict, description="Non-secret environment from the Dockerfile.")
    unresolved: list[str] = Field(
        default_factory=list,
        description="Fields the project cannot state about itself; the caller must supply these.",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal notes about the derivation.")


class InspectAgentRequest(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/manifests/inspect-agent`` — a deployed agent ref."""

    agent: str = Field(description="Deployed agent reference (``workspace/name`` or ``name``).")


class InspectAgentResponse(BaseModel):
    """Auto-derived defaults for the deployed-agent create form (port + secret names, editable)."""

    agent: str = Field(description="Resolved ``workspace/name`` of the agent.")
    port: int = Field(description="Victim port derived from the running deployment (else the default).")
    secrets: list[str] = Field(default_factory=list, description="Secret names derived from the agent config.")
    egress: list[str] = Field(
        default_factory=list,
        description="Hosts the agent's own config names (model endpoints, network MCP servers). Shown so "
        "the form does not read as 'no egress' for an agent that has some.",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal notes (e.g. no running deployment).")


class ManifestUpdate(BaseModel):
    """Body for ``PATCH /v2/workspaces/{workspace}/manifests/{name}`` — edit an existing manifest.

    Only editable fields; omitted fields are left unchanged. The agent source is immutable (delete +
    recreate to retarget).
    """

    benign_suite: list[dict[str, str]] | None = Field(
        default=None, description="Replace the cached benign suite (tool,payload,label,rationale,persona rows)."
    )
    port: int | None = Field(default=None, description="Victim port the war-game will target.")
    egress: list[str] | None = Field(
        default=None, description="Allow-listed egress host[:port] entries the victim may reach."
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Non-secret environment variables for the victim (agent-hardener's `agent.env`). Stored in "
        "plaintext on the manifest — credentials belong in `secrets`, which names them and "
        "resolves the values from the Secrets store at run time.",
    )
    defenders: list[str] | None = Field(
        default=None,
        description="Enabled defender keys ('guardrails','openshell'); empty means agent-hardener defaults.",
    )
    attack_intensity: Literal["light", "standard", "thorough"] | None = Field(
        default=None, description="Attacker (garak) effort preset."
    )
    rounds: int | None = Field(
        default=None, ge=1, description="Number of iterative hardening rounds (agent-hardener `run --rounds`)."
    )
    models: WarGameModels | None = Field(
        default=None, description="Replace the stored default model selection (attack/analysis/agent groups)."
    )


class ApplyMitigationRequest(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/runs/{name}/apply-mitigation`` — adopt the hardened workflow.

    The client passes the hardened workflow YAML from the run's mitigations artifact. The endpoint reverses
    the Inference-Gateway injection and writes it onto the run's target agent config (no redeploy).
    """

    guardrails_toml: str = Field(description="Hardened Relay guardrail set (the mitigations 'after' document).")


class ApplyMitigationResponse(BaseModel):
    """Result of applying a hardened workflow to an agent."""

    applied: bool = Field(description="True when the agent config was updated.")
    agent: str = Field(description="Name of the agent whose config was updated.")
    detail: str = Field(description="Human-readable note (e.g. a reminder to redeploy).")


class ComposeDefenseRequest(BaseModel):
    """Body for ``POST /v2/workspaces/{workspace}/runs/{name}/compose-defense`` — build a chosen defense subset.

    The client passes the run's ``mitigations`` artifact (which it already fetched for the recommendations
    view) plus the ids of the defenses to keep. The endpoint composes the workflow with only the selected
    guardrails and picks the hardened-vs-baseline policy, for live preview and to feed a sanity-check run.
    """

    mitigations: dict[str, Any] = Field(description="The run's mitigations artifact (its 'defenses'/workflow/policy).")
    selected_defense_ids: list[str] = Field(
        default_factory=list, description="Ids of the defenses to keep (guardrail ids and/or 'openshell_policy')."
    )


class ComposeDefenseResponse(BaseModel):
    """The composed workflow + policy for the selected defenses."""

    guardrails_toml: str | None = Field(
        default=None, description="Plugin config with only the selected guardrails, or null."
    )
    policy_yaml: str | None = Field(
        default=None, description="Hardened policy if selected, else the baseline, or null."
    )
