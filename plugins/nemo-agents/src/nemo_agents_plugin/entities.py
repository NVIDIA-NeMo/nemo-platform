# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent entity definitions — stored in the NeMo Platform entity store.

This module contains only entity classes (subclasses of
:class:`~nemo_platform_plugin.entity.NemoEntity`).  API request/response schemas and
filter models live in :mod:`nemo_agents_plugin.schema`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from nemo_platform_plugin.entity import NemoEntity
from nemo_platform_plugin.refs import FilesetRef
from pydantic import BaseModel, Field

DeploymentStatus = Literal["pending", "starting", "running", "failed", "deleting"]


class SessionStatus(StrEnum):
    """Lifecycle status of an agent session."""

    ACTIVE = "active"
    EXPIRED = "expired"
    LOST = "lost"
    CLOSED = "closed"

    def can_transition_to(self, new_status: SessionStatus) -> bool:
        """Return whether transitioning to *new_status* is allowed."""
        if self == new_status:
            return True

        valid_transitions = {
            SessionStatus.ACTIVE: {
                SessionStatus.EXPIRED,
                SessionStatus.LOST,
                SessionStatus.CLOSED,
            },
            SessionStatus.EXPIRED: {SessionStatus.CLOSED},
            SessionStatus.LOST: {SessionStatus.CLOSED},
            SessionStatus.CLOSED: set(),
        }
        return new_status in valid_transitions[self]


# Runtime backend for an AgentDeployment. ``subprocess`` (the default) runs the
# agent as a local ``nat serve`` process reachable on a loopback ``endpoint``.
# ``docker``/``k8s`` run the agent as a durable container deployment via the
# deployments plugin; their routable address is projected onto ``endpoints``.
DeploymentMode = Literal["subprocess", "docker", "k8s"]

# Modes that compile to the nemo-deployments plugin (not local subprocess).
CONTAINER_DEPLOYMENT_MODES: frozenset[str] = frozenset({"docker", "k8s"})


def is_container_deployment_mode(mode: str) -> bool:
    """Return True when *mode* uses the deployments-plugin runner backend."""
    return mode in CONTAINER_DEPLOYMENT_MODES


class Endpoint(BaseModel):
    """A routable network endpoint for a deployment.

    Mirrors ``nemo_deployments_plugin.types.Endpoint`` so container-mode
    deployments can carry the address the deployments-plugin ``Deployment``
    projected without the agents plugin depending on that plugin at the
    entity-schema layer.
    """

    name: str
    url: str
    protocol: Literal["http", "https", "grpc", "tcp"] = "http"


# ---------------------------------------------------------------------------
# AgentEnvironment composition
# ---------------------------------------------------------------------------
#
# An AgentDeployment (and, later, an AgentInvocationJob) runs against an
# AgentEnvironment: a composition of an EnvironmentSpec (the dependencies an
# agent reaches - model endpoints, secrets, env vars, MCP servers) and a
# ComputeSpec (k8s-style resource requests/limits). Each part varies
# independently and is referenced by ``ref | inline | None`` so a spec can be
# authored once and reused across many Environments.
#
# The specs are also first-class entities (``agent_environment_spec``,
# ``agent_compute_spec``, ``agent_environment``) with their own CRUD APIs. The
# inline BaseModels below are the shared shape: an entity embeds the inline
# fields, and an AgentEnvironment field accepts either a ``"workspace/name"``
# ref string or the inline model.
#
# Environment values compile into two targets at deploy time: the on-disk
# agent.yaml / FabricConfig (env vars, MCP, model provider) and, for container
# modes, the deployments-plugin Container.resources (compute). See
# :mod:`nemo_agents_plugin.environment_resolution` for the merge + snapshot.


class ComputeResources(BaseModel):
    """Kubernetes-style resource requests/limits.

    Mirrors ``nemo_deployments_plugin.entities.ResourceRequirements`` so the
    agents entity schema does not depend on the deployments plugin. Compiled
    into the execute container's resources for container deployment modes.
    """

    limits: dict[str, str] = Field(
        default_factory=dict,
        description="k8s resource limits (e.g. cpu, memory, nvidia.com/gpu).",
    )
    requests: dict[str, str] = Field(
        default_factory=dict,
        description="k8s resource requests.",
    )


class ComputeSpecInline(BaseModel):
    """Inline compute spec - the resources an invocation runs with."""

    description: str = Field(default="", description="Human-readable description.")
    resources: ComputeResources = Field(
        default_factory=ComputeResources,
        description="k8s-style resource requests/limits for the execute container.",
    )


class ModelProviderOverride(BaseModel):
    """Exceptional external model-provider override.

    Null in the normal case: model selection is on the Agent and the provider
    URL is the Inference Gateway (auto-injected). Set ONLY to point the agent at
    a non-IGW external provider endpoint.
    """

    base_url: str = Field(description="External model-provider endpoint.")
    api_key: str | None = Field(
        default=None,
        description="Secrets-service ref for the provider API key (only needed for external providers).",
    )
    provider: str | None = Field(
        default=None,
        description='Provider selector (e.g. "openai", "anthropic").',
    )


class McpFulfillment(BaseModel):
    """EnvironmentSpec-side fulfillment for one MCP server the Agent declares.

    The Agent DECLARES an MCP dependency by name; the EnvironmentSpec PROVIDES
    the url + env + secrets for that same name. Matched by server-name key at
    compile time; ``secrets`` are merged into the server's ``env``.
    """

    url: str = Field(description="Endpoint the environment provides for this MCP server.")
    env: dict[str, str] = Field(default_factory=dict, description="Non-secret env for the MCP server.")
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description="ENV_NAME -> Secrets-service ref, merged into the MCP server env at compile.",
    )


class EnvironmentSpecInline(BaseModel):
    """Inline environment spec - the dependencies and configuration an agent reaches.

    This is the fulfillment half of a request/fulfill split: the Agent declares
    the dependencies it needs; the EnvironmentSpec provides concrete endpoints
    and secret references. It compiles into the agent.yaml / FabricConfig and
    the injected process environment.
    """

    description: str = Field(default="", description="Human-readable description.")

    # Env vars -> injected into the runtime process env (not authored on disk).
    env: dict[str, str] = Field(default_factory=dict, description="Plaintext, non-secret env vars.")

    # Secrets -> Secrets-service refs, injected as secret-backed env vars.
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description="ENV_VAR_NAME -> Secrets-service/plugin ref.",
    )

    # External model-provider override (exceptional; null in the normal IGW case).
    model_provider_override: ModelProviderOverride | None = Field(
        default=None,
        description="Set only to point at a non-IGW external model provider.",
    )

    # Fabric environment mirror -> compiles into FabricConfig.environment.
    # NOTE: ``workspace_path`` (the harness workspace path) is deliberately named
    # to avoid colliding with the NeMo entity ``workspace`` (tenant) field that
    # AgentEnvironmentSpec inherits from EntityBase. ``artifacts_path`` carries a
    # matching ``_path`` suffix for symmetry.
    provider: str = Field(default="local", description="local | docker | opensandbox | k8s.")
    workspace_path: str | None = Field(default=None, description="Workspace path visible to the harness.")
    artifacts_path: str | None = Field(default=None, description="Provider-specific artifact output location.")
    control_location: str | None = Field(
        default=None,
        description="external_control | in_env_control.",
    )
    ownership: str | None = Field(default=None, description="caller_owned | fabric_owned.")
    connection: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider connection metadata (server url, cred ref, namespace).",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Consumer-provided passthrough metadata.")
    settings: dict[str, Any] = Field(default_factory=dict, description="Provider-specific settings.")

    # MCP fulfillment -> merged into FabricConfig.mcp.servers.<name> by server-name key.
    mcp: dict[str, McpFulfillment] = Field(
        default_factory=dict,
        description="server-name -> fulfillment (url/env/secrets) for an Agent-declared MCP dependency.",
    )


class AgentEnvironmentInline(BaseModel):
    """Inline AgentEnvironment - a composition of environment + compute specs.

    Each part is a ``ref | inline | None`` union: a ``"workspace/name"`` string
    references a stored spec entity, an object provides the spec inline, and
    ``None`` omits it. (A ``sandbox_spec`` is out of scope for now and omitted.)
    """

    description: str = Field(default="", description="Human-readable description.")
    environment_spec: str | EnvironmentSpecInline | None = Field(
        default=None,
        description='"workspace/name" ref to an AgentEnvironmentSpec, an inline spec, or None.',
    )
    compute_spec: str | ComputeSpecInline | None = Field(
        default=None,
        description='"workspace/name" ref to an AgentComputeSpec, an inline spec, or None.',
    )


# ---------------------------------------------------------------------------
# Canonical Ethos storage convention
# ---------------------------------------------------------------------------
#
# Each agent has exactly one Ethos fileset, named by convention. The fileset can
# hold both the human-readable Ethos document and the machine-readable agent
# config. We do **not** store these locations on the agent - they are fully
# derivable from the agent's workspace and name. Consumers should call the
# file-ref helpers below rather than reconstructing refs inline.
#
# Layout:
#   - Fileset (entity ref):  ``{workspace}/{agent-name}-ethos``
#   - Human-readable Ethos:  ``ETHOS.md``
#   - Machine-readable cfg:  ``agent.yaml``
#   - Ethos file ref:        ``{workspace}/{agent-name}-ethos#ETHOS.md``
#   - Config file ref:       ``{workspace}/{agent-name}-ethos#agent.yaml``
#   - Local cache root:      ``agents/{agent-name}-ethos/``
#
# This is intentionally **not** an Optional field on the Agent. The
# relationship is 1:1 and convention-bound; carrying a stored ref would
# duplicate state with no resilience benefit (rename of either entity
# orphans both representations equally).

ETHOS_FILENAME = "ETHOS.md"
"""Canonical filename inside the agent's Ethos fileset."""

AGENT_SPEC_FILENAME = "AGENT-SPEC.md"
"""Prior contract filename. Staging drops it from the runtime tree."""

AGENT_CONFIG_FILENAME = "agent.yaml"
"""Canonical machine-readable agent config filename in the agent Ethos fileset.

This file is parsed into Agent.config when using the nemo-agents-spec-v1 format.
"""

ETHOS_LOCAL_ROOT = "agents"
"""Local directory holding agent build artifacts."""

NAT_WORKFLOW_CONFIG_FORMAT = "nat-workflow-v1"
"""Canonical format tag for the legacy NAT workflow config format."""

NEMO_AGENTS_SPEC_CONFIG_FORMAT = "nemo-agents-spec-v1"
"""Canonical format tag for the Platform-owned agent.yaml spec format."""


class AgentInline(BaseModel):
    """Inline Agent - an agent definition without entity identity.

    The shared shape behind the :class:`Agent` entity: the entity embeds these
    fields and adds name/workspace, and a field that accepts an agent can take
    either a ``"workspace/name"`` ref string or this model. Lets a caller
    execute an agent it composes at request time — models chosen per request,
    settings scoped to one run — without first persisting an Agent.

    Deliberately as permissive as the entity: consumers impose their own
    requirements rather than this model narrowing them for everyone. The
    ``agents.execute`` job, for example, accepts only ``nemo-agents-spec-v1``
    and rejects a config that is not a valid agent spec.
    """

    description: str = Field(default="", description="Human-readable description of the agent.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent config dict interpreted according to config_format.",
    )
    config_format: str = Field(
        default=NAT_WORKFLOW_CONFIG_FORMAT,
        description=(
            "platform-internal schema version tag for the agent config dict. "
            "`nat-workflow-v1` is the default legacy NAT workflow format; "
            "`nemo-agents-spec-v1` identifies the Platform-owned agent.yaml spec format."
        ),
    )


# Container deployments deliver the Ethos fileset through a ConfigMap (k8s) or a
# single env var (docker), both of which cap out around 1MiB. Bound the tree at
# both ends of the pipe so an agent root pointed at a whole checkout fails at
# upload time with a clear message instead of at container start.
MAX_ETHOS_STAGED_BYTES = 900_000
"""Maximum total bytes an agent Ethos fileset may contribute to a deployment."""

MAX_ETHOS_STAGED_FILES = 500
"""Maximum number of files an agent Ethos fileset may contain."""


def ethos_fileset_name(agent_name: str) -> str:
    """Return the conventional fileset name holding an agent's Ethos."""
    return f"{agent_name}-ethos"


def ethos_local_path(agent_name: str, root: str | Path = ETHOS_LOCAL_ROOT) -> Path:
    """Return the local write-through cache path for an agent's Ethos."""
    return Path(root) / ethos_fileset_name(agent_name) / ETHOS_FILENAME


def ethos_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-ethos#ETHOS.md``.

    Use this anywhere downstream code needs to point at an agent's Ethos -
    do not reconstruct the path inline. If the layout ever changes (e.g.
    moving to a per-agent bundle fileset holding multiple artifacts), this
    is the only function that needs to update.
    """
    return FilesetRef(f"{workspace}/{ethos_fileset_name(agent_name)}#{ETHOS_FILENAME}")


def agent_config_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-ethos#agent.yaml``.

    Use this anywhere downstream code needs to point at an agent's config -
    do not reconstruct the path inline. If the layout ever changes (e.g.
    moving to a per-agent bundle fileset holding multiple artifacts), this
    is the only function that needs to update.
    """
    return FilesetRef(f"{workspace}/{ethos_fileset_name(agent_name)}#{AGENT_CONFIG_FILENAME}")


class AgentComputeSpec(NemoEntity, ComputeSpecInline, entity_type="agent_compute_spec"):
    """A reusable compute spec (k8s-style resource requests/limits).

    Entity type: ``agent_compute_spec``
    Referenced by an AgentEnvironment's ``compute_spec`` (by name or inline).
    """


class AgentEnvironmentSpec(NemoEntity, EnvironmentSpecInline, entity_type="agent_environment_spec"):
    """A reusable environment spec (the dependencies an agent reaches).

    Entity type: ``agent_environment_spec``
    Referenced by an AgentEnvironment's ``environment_spec`` (by name or inline).
    """


class AgentEnvironment(NemoEntity, AgentEnvironmentInline, entity_type="agent_environment"):
    """A composition of an environment spec and a compute spec.

    Entity type: ``agent_environment``
    The single thing an AgentDeployment references. Each part is a
    ``ref | inline | None`` union so specs can be authored once and reused.
    """


# TODO: first-class environment, sandbox, and harness specs are planned for the
# Agent entity. Add those specs to this object once the contract is finalized.
class Agent(NemoEntity, AgentInline, entity_type="agent"):
    """An agent definition — stores agent config and metadata.

    Entity type: ``agent``
    Primary lookup: by ``name`` within a ``workspace``.

    The agent's Ethos files live at the locations returned by
    :func:`ethos_file_ref` and :func:`agent_config_file_ref` — they
    are **not** stored on the entity because the paths are fully derivable
    from ``(workspace, name)``.
    """


class AgentDeployment(NemoEntity, entity_type="agent_deployment"):
    """A running (or pending) deployment of an Agent.

    Entity type: ``agent_deployment``
    Lifecycle: pending → starting → running | failed.
    The :class:`~nemo_agents_plugin.runner.controller.AgentDeploymentController`
    drives state transitions by reconciling this entity against the
    :class:`~nemo_agents_plugin.runner.backend.RunnerBackend`.
    """

    agent: str = Field(default="", description="Name of the Agent entity this deployment is for.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Resolved agent config with IGW URL injected and any referenced environment spec merged in, "
            "written when the deployment is created."
        ),
    )
    # AgentEnvironment is snapshotted at create time: ``environment`` records the
    # raw request input for provenance, environment-spec content is merged into
    # ``config``, ``compute`` holds the resolved compute snapshot, and ``secrets``
    # holds the resolved secret-env references — all threaded to the container
    # backend. A deployment is not kept in sync with the underlying
    # AgentEnvironment/spec entities after creation.
    environment: str | AgentEnvironmentInline | None = Field(
        default=None,
        description=(
            '"workspace/name" ref to an AgentEnvironment, an inline environment, or None. '
            "Snapshotted at create time for provenance; the resolved values live in config/compute/secrets."
        ),
    )
    compute: ComputeSpecInline | None = Field(
        default=None,
        description=(
            "Resolved compute snapshot from the referenced environment. Compiled into the container "
            "resources for docker/k8s modes; ignored for subprocess."
        ),
    )
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Resolved secret env references from the referenced environment, as "
            "ENV_VAR_NAME -> 'workspace/secret-name'. Compiled into secret-backed container env "
            "vars (never plaintext) for docker/k8s modes; ignored for subprocess."
        ),
    )
    status: DeploymentStatus = Field(
        default="pending",
        description="Lifecycle status: pending | starting | running | failed | deleting.",
    )
    deployment_mode: DeploymentMode = Field(
        default="subprocess",
        description=(
            "Runtime backend for this deployment. 'subprocess' (default) reads the loopback "
            "'endpoint'; 'docker'/'k8s' read the projected 'endpoints'."
        ),
    )
    # Dual addressing: subprocess uses loopback ``endpoint``; docker/k8s project
    # routable addresses onto ``endpoints`` and leave ``endpoint`` empty.
    endpoint: str = Field(
        default="", description="Subprocess loopback endpoint of the agent process (e.g. http://localhost:9001)."
    )
    endpoints: list[Endpoint] = Field(
        default_factory=list,
        description=(
            "Routable endpoints for container modes, projected from the deployments-plugin "
            "Deployment. Empty for subprocess mode (which uses 'endpoint')."
        ),
    )
    image: str = Field(
        default="",
        description="Container image for docker/k8s modes. Empty for subprocess; falls back to AgentsConfig.deployments.default_image.",
    )
    use_image_entrypoint: bool = Field(
        default=False,
        description=(
            "Container modes only: preserve the image ENTRYPOINT/CMD instead of injecting "
            "the platform-owned NAT/Fabric server command."
        ),
    )
    plugin_deployment: str = Field(
        default="",
        description=(
            "Name of the linked nemo-deployments Deployment entity. Defaults to this "
            "deployment's name when empty (set by the controller on create)."
        ),
    )
    port: int = Field(default=0, description="Port the agent process is listening on.")
    pid: int = Field(default=0, description="OS process ID of the agent subprocess.")
    error: str = Field(default="", description="Error message if status is 'failed'.")


class AgentSession(NemoEntity, entity_type="agent_session"):
    """A durable logical conversation associated with an AgentDeployment.

    The session entity owns Platform-level conversation identity only. Live
    harness state remains process-local to the deployment's serving runtime.
    """

    deployment_id: str = Field(
        min_length=1,
        description="Immutable ID of the AgentDeployment this session belongs to.",
    )
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        description="Lifecycle status: active | expired | lost | closed.",
    )
    first_active_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of the first accepted invocation; immutable once set.",
        json_schema_extra={"nullable": True},
    )
    last_active_at: datetime | None = Field(
        default=None,
        description=(
            "UTC timestamp of the latest accepted or completed invocation; null until the first invocation is accepted."
        ),
        json_schema_extra={"nullable": True},
    )
    expires_at: datetime | None = Field(
        default=None,
        description="UTC rolling idle deadline derived from the latest session activity.",
        json_schema_extra={"nullable": True},
    )
