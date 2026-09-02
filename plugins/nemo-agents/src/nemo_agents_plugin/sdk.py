# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resource class for the Agents plugin.

Registered under the ``nemo.sdk`` entry-point group. The platform lazily
instantiates this plugin's sync or async SDK resource as ``client.agents``.

Usage (once the SDK hub is wired up)::

    from nemoplatform import NeMo

    nemo = NeMo(base_url="http://localhost:8000")

    # Agent CRUD
    agent = nemo.agents.create(name="calculator", config={...})
    agents = nemo.agents.list()
    agent = nemo.agents.get("calculator")
    nemo.agents.delete("calculator")

    # Deployment lifecycle
    dep = nemo.agents.deployments.create(agent="calculator")  # subprocess
    dep = nemo.agents.deployments.create(
        agent="calculator", deployment_mode="docker", image="calculator:local"
    )
    deps = nemo.agents.deployments.list()
    dep = nemo.agents.deployments.get("calculator-a1b2")
    nemo.agents.deployments.delete("calculator-a1b2")

    # Environments / specs (the request/fulfill split)
    spec = nemo.agents.environment_specs.create(
        name="ben",
        spec=EnvironmentSpecInline(
            env={"LOG_LEVEL": "debug"},
            secrets={"GITHUB_PERSONAL_ACCESS_TOKEN": "default/ben-pat"},
        ),
    )
    env = nemo.agents.environments.create(name="repo-research-ben", environment_spec="default/ben")
    cs = nemo.agents.compute_specs.create(
        name="big", spec=ComputeSpecInline(resources=ComputeResources(limits={"cpu": "2"})),
    )
    dep = nemo.agents.deployments.create(agent="calculator", environment="default/repo-research-ben")

    # Invocation (routes through the agents gateway)
    result = nemo.agents.invoke(agent="calculator", input="What is 2+2?")
    result = nemo.agents.invoke(
        deployment="calculator-a1b2",
        session_id="session-entity-id",
        input="Continue",
    )

    # agents.execute jobs
    job = nemo.agents.jobs.execute.create(spec={"agent": "calculator", "input": "What is 2+2?"})
    job = nemo.agents.jobs.execute.get(job["name"])
    results = nemo.agents.jobs.execute.list_results(job["name"])

An async namespace is mounted as ``client.agents`` on ``AsyncNeMoPlatform``.
It currently exposes ``jobs`` only — agent CRUD, deployments, and ``invoke``
remain sync-only.
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping

import httpx
from nemo_agents_plugin.entities import (
    AgentEnvironmentInline,
    ComputeSpecInline,
    EnvironmentSpecInline,
)
from nemo_agents_plugin.session_protocol import SESSION_ID_HEADER
from nemo_platform_plugin.sdk import NemoPluginSDKResources
from pydantic import BaseModel

_DEFAULT_WORKSPACE = "default"
_DEFAULT_TIMEOUT = 30
_DEFAULT_MODEL_PLACEHOLDER = re.compile(r"\$(?:\{NEMO_DEFAULT_MODEL\}|NEMO_DEFAULT_MODEL(?![A-Za-z0-9_]))")


def _resolve_workspace(platform: Any, workspace: str | None) -> str:
    return workspace or getattr(platform, "workspace", None) or _DEFAULT_WORKSPACE


def _spec_to_dict(spec: BaseModel | dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a typed ``*Inline`` model (or a loose dict) to a request body.

    Accepts one of the shared backend ``*Inline`` models, a plain dict, or
    ``None``. Pydantic models are dumped with ``exclude_unset=True`` so only the
    fields the caller actually set are sent — matching the ``**spec`` behavior
    where unspecified fields simply were not in the payload.
    """
    if spec is None:
        return {}
    if isinstance(spec, BaseModel):
        return spec.model_dump(exclude_unset=True, mode="json")
    return dict(spec)


def _contains_default_model_placeholder(value: Any) -> bool:
    """Return True when *value* still contains an unresolved default-model placeholder."""
    if isinstance(value, str):
        protected = value.replace("$$", "\0DOLLAR\0")
        return _DEFAULT_MODEL_PLACEHOLDER.search(protected) is not None
    if isinstance(value, dict):
        return any(_contains_default_model_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_default_model_placeholder(v) for v in value)
    return False


class AgentsResource:
    """SDK namespace for ``nemo.agents.*``."""

    def __init__(self, platform: Any) -> None:
        """
        Args:
            platform: The ``NeMo`` hub object (or any object with a
                ``base_url`` attribute).  Provides the base URL for all API calls.
                An optional ``default_headers`` attribute (a ``dict[str, str]``)
                is attached to every request — this is how the CLI threads its
                resolved auth token through the SDK.
        """
        self._platform = platform
        self._deployments: _DeploymentResource | None = None
        self._environments: _EnvironmentResource | None = None
        self._environment_specs: _EnvironmentSpecResource | None = None
        self._compute_specs: _ComputeSpecResource | None = None
        self._jobs: _JobsResource | None = None

    # ------------------------------------------------------------------
    # Agent CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        config: dict[str, Any],
        description: str = "",
        config_format: str = "nat-workflow-v1",
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Create a new agent.

        Args:
            name: Unique agent name within the workspace.
            config: NAT workflow config dict.
            description: Optional human-readable description.
            config_format: Config format identifier (default: ``"nat-workflow-v1"``).
            workspace: Target workspace. Defaults to the workspace configured
                on the platform client, or ``"default"`` when the client has no
                workspace.

        Returns:
            The created agent as a dict.
        """
        from nemo_agents_plugin.utils import inject_default_model

        resolved_config = inject_default_model(config)
        if _contains_default_model_placeholder(resolved_config):
            raise ValueError(
                "Agent config references ${NEMO_DEFAULT_MODEL}, but no default model is selected. "
                "Run `nemo setup`, set NEMO_DEFAULT_MODEL, or replace the placeholder with an explicit "
                "VirtualModel name."
            )
        payload = {
            "name": name,
            "config": resolved_config,
            "description": description,
            "config_format": config_format,
        }
        return self._post(f"/v2/workspaces/{self._workspace(workspace)}/agents", payload)

    def list(self, workspace: str | None = None) -> List[dict[str, Any]]:
        """List agents in *workspace*."""
        return self._get(f"/v2/workspaces/{self._workspace(workspace)}/agents")

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get an agent by name."""
        return self._get(f"/v2/workspaces/{self._workspace(workspace)}/agents/{name}")

    def delete(self, name: str, workspace: str | None = None) -> None:
        """Delete an agent by name."""
        self._delete(f"/v2/workspaces/{self._workspace(workspace)}/agents/{name}")

    # ------------------------------------------------------------------
    # Deployment sub-resource
    # ------------------------------------------------------------------

    @property
    def deployments(self) -> _DeploymentResource:
        """Sub-resource for deployment lifecycle operations."""
        if self._deployments is None:
            self._deployments = _DeploymentResource(self)
        return self._deployments

    @property
    def environments(self) -> _EnvironmentResource:
        """Sub-resource for AgentEnvironment CRUD (``nemo.agents.environments``)."""
        if self._environments is None:
            self._environments = _EnvironmentResource(self)
        return self._environments

    @property
    def environment_specs(self) -> _EnvironmentSpecResource:
        """Sub-resource for AgentEnvironmentSpec CRUD (``nemo.agents.environment_specs``)."""
        if self._environment_specs is None:
            self._environment_specs = _EnvironmentSpecResource(self)
        return self._environment_specs

    @property
    def compute_specs(self) -> _ComputeSpecResource:
        """Sub-resource for AgentComputeSpec CRUD (``nemo.agents.compute_specs``)."""
        if self._compute_specs is None:
            self._compute_specs = _ComputeSpecResource(self)
        return self._compute_specs

    @property
    def jobs(self) -> "_JobsResource":
        """Sub-resource for agents job collections."""
        if self._jobs is None:
            self._jobs = _JobsResource(self._platform)
        return self._jobs

    # ------------------------------------------------------------------
    # Invocation and evaluation
    # ------------------------------------------------------------------

    def invoke(
        self,
        *,
        input: str,
        agent: str | None = None,
        deployment: str | None = None,
        session_id: str | None = None,
        workspace: str | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """Send a single request to an agent via the gateway.

        Args:
            input: The user message / query string.
            agent: Agent name (gateway resolves the active deployment).
            deployment: Deployment name (direct targeting).
            session_id: Optional persisted Platform session entity ID. Sent in
                the ``X-Nemo-Session-Id`` request header.
            workspace: Workspace.
            timeout: Request timeout in seconds.

        Returns:
            The agent's response as a dict.
        """
        resolved_workspace = self._workspace(workspace)
        if agent:
            path = f"/v2/workspaces/{resolved_workspace}/agents/{agent}/-/v1/chat/completions"
        elif deployment:
            path = f"/v2/workspaces/{resolved_workspace}/deployments/{deployment}/-/v1/chat/completions"
        else:
            raise ValueError("Provide either agent= or deployment=.")
        if session_id == "":
            raise ValueError("session_id must not be empty.")

        payload = {
            "messages": [{"role": "user", "content": input}],
            "stream": False,
        }
        headers = {SESSION_ID_HEADER: session_id} if session_id is not None else None
        return self._post(path, payload, timeout=timeout, headers=headers)

    def evaluate(
        self,
        *,
        eval_config: str,
        agent: str | None = None,
        endpoint: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Trigger an evaluation run.

        .. note::
            Platform-managed evaluation is not yet implemented.
            Use the CLI instead::

                nemo agents evaluate --eval-config <path>
                nemo agents evaluate --eval-config <path> --agent <name>

        Raises:
            NotImplementedError: Always — platform-managed evaluation is not
                yet available.  Use ``nemo agents evaluate`` CLI instead.
        """
        raise NotImplementedError(
            "Platform-managed evaluation is not yet implemented. "
            "Use the CLI: nemo agents evaluate --eval-config <path> [--agent <name>]"
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        base = getattr(self._platform, "base_url", "http://localhost:8000")
        return str(base).rstrip("/")

    def _workspace(self, workspace: str | None) -> str:
        return _resolve_workspace(self._platform, workspace)

    def _agents_url(self, path: str) -> str:
        return self._base_url() + "/apis/agents" + path

    def _default_headers(self) -> dict[str, str] | None:
        headers = getattr(self._platform, "default_headers", None)
        if isinstance(headers, dict) and headers:
            return {str(key): str(value) for key, value in headers.items()}
        return None

    def _get(self, path: str) -> Any:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.get(self._agents_url(path), headers=self._default_headers())
            resp.raise_for_status()
            return resp.json()

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: int = _DEFAULT_TIMEOUT,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        merged = {**(self._default_headers() or {}), **(headers or {})} or None
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._agents_url(path), json=payload, headers=merged)
            resp.raise_for_status()
            return resp.json()

    def _delete(self, path: str) -> None:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.delete(self._agents_url(path), headers=self._default_headers())
            resp.raise_for_status()


class _DeploymentResource:
    """Deployment lifecycle operations under ``nemo.agents.deployments``."""

    def __init__(self, parent: AgentsResource) -> None:
        self._parent = parent

    def create(
        self,
        *,
        agent: str,
        name: str | None = None,
        deployment_mode: str = "subprocess",
        image: str | None = None,
        use_image_entrypoint: bool = False,
        environment: str | dict[str, Any] | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Create a deployment for *agent*.

        Args:
            agent: Name of the agent to deploy.
            name: Deployment name (auto-generated if omitted).
            deployment_mode: Runtime backend — ``"subprocess"`` (default),
                ``"docker"``, or ``"k8s"``. Container modes run the agent as a
                durable container through the deployments plugin and require a
                configured executor.
            image: Container image for ``docker``/``k8s`` modes. Falls back to
                ``agents.deployments.default_image`` when omitted. Rejected in
                ``subprocess`` mode.
            use_image_entrypoint: For ``docker``/``k8s`` modes, preserve the
                image ENTRYPOINT/CMD instead of injecting the platform-owned
                agent server command.
            environment: Optional AgentEnvironment to deploy under — a
                ``"workspace/name"`` ref to a stored AgentEnvironment, or an
                inline environment dict. Its EnvironmentSpec is merged into the
                agent config and its ComputeSpec/secret refs are snapshotted onto
                the deployment at creation time.
            workspace: Target workspace.

        Returns:
            The created deployment as a dict.
        """
        if image and deployment_mode == "subprocess":
            raise ValueError("image requires deployment_mode='docker' or 'k8s'.")
        if use_image_entrypoint and deployment_mode == "subprocess":
            raise ValueError("use_image_entrypoint requires deployment_mode='docker' or 'k8s'.")
        payload: dict[str, Any] = {"agent": agent, "deployment_mode": deployment_mode}
        if name:
            payload["name"] = name
        if image:
            payload["image"] = image
        if use_image_entrypoint:
            payload["use_image_entrypoint"] = True
        if environment is not None:
            payload["environment"] = environment
        return self._parent._post(f"/v2/workspaces/{self._parent._workspace(workspace)}/deployments", payload)

    def list(self, workspace: str | None = None) -> List[dict[str, Any]]:
        """List all deployments in *workspace*."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/deployments")

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a deployment by name."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/deployments/{name}")

    def delete(self, name: str, workspace: str | None = None) -> None:
        """Mark a deployment for deletion."""
        self._parent._delete(f"/v2/workspaces/{self._parent._workspace(workspace)}/deployments/{name}")


class _EnvironmentSpecResource:
    """AgentEnvironmentSpec CRUD under ``nemo.agents.environment_specs``.

    An EnvironmentSpec is the fulfillment half of the request/fulfill split: the
    Agent declares the dependencies it needs; the spec provides concrete
    endpoints, plaintext env, and secret refs. It is merged into the agent config
    at deployment/job create time.
    """

    def __init__(self, parent: AgentsResource) -> None:
        self._parent = parent

    def create(
        self,
        *,
        name: str,
        spec: EnvironmentSpecInline | dict[str, Any] | None = None,
        workspace: str | None = None,
        **spec_kwargs: Any,
    ) -> dict[str, Any]:
        """Create an environment spec.

        Args:
            name: Unique environment-spec name within the workspace.
            spec: The environment spec, as a shared :class:`EnvironmentSpecInline`
                model (the typed, discoverable path) or a plain dict. Only the
                fields explicitly set on the model are sent.
            workspace: Target workspace.
            **spec_kwargs: Back-compat loose EnvironmentSpecInline fields (``env``,
                ``secrets``, ``mcp``, ``provider``, ``model_provider_override``,
                ``workspace_path``, ``artifacts_path``, ``connection``,
                ``metadata``, ``settings``, ...). Merged over ``spec`` when both
                are given. Prefer the typed ``spec=`` argument.

        Returns:
            The created AgentEnvironmentSpec as a dict.
        """
        payload: dict[str, Any] = {**_spec_to_dict(spec), **spec_kwargs, "name": name}
        return self._parent._post(f"/v2/workspaces/{self._parent._workspace(workspace)}/environment-specs", payload)

    def list(self, workspace: str | None = None) -> List[dict[str, Any]]:
        """List environment specs in *workspace*."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/environment-specs")

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get an environment spec by name."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/environment-specs/{name}")

    def delete(self, name: str, workspace: str | None = None) -> None:
        """Delete an environment spec by name."""
        self._parent._delete(f"/v2/workspaces/{self._parent._workspace(workspace)}/environment-specs/{name}")


class _EnvironmentResource:
    """AgentEnvironment CRUD under ``nemo.agents.environments``.

    An AgentEnvironment composes an ``environment_spec`` and a ``compute_spec``
    (each a ``"workspace/name"`` ref or an inline object). It is the single thing
    a deployment or execute job references via its ``environment`` field.
    """

    def __init__(self, parent: AgentsResource) -> None:
        self._parent = parent

    def create(
        self,
        *,
        name: str,
        spec: AgentEnvironmentInline | dict[str, Any] | None = None,
        environment_spec: str | dict[str, Any] | None = None,
        compute_spec: str | dict[str, Any] | None = None,
        description: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Create an AgentEnvironment.

        Args:
            name: Unique environment name within the workspace.
            spec: The full environment composition as a shared
                :class:`AgentEnvironmentInline` model (the typed, discoverable
                path) or a plain dict. Only the fields explicitly set are sent.
                The ``environment_spec`` / ``compute_spec`` / ``description``
                arguments below override the matching keys from ``spec`` when
                given — handy for the common ref case.
            environment_spec: A ``"workspace/name"`` ref to a stored
                AgentEnvironmentSpec, an inline spec dict, or ``None``.
            compute_spec: A ``"workspace/name"`` ref to a stored AgentComputeSpec,
                an inline spec dict, or ``None``.
            description: Optional human-readable description. Overrides ``spec``'s
                description when passed (including ``""`` to clear it); left unset,
                ``spec``'s value — or the server default — stands.
            workspace: Target workspace.

        Returns:
            The created AgentEnvironment as a dict.
        """
        payload: dict[str, Any] = {**_spec_to_dict(spec), "name": name}
        if description is not None:
            payload["description"] = description
        if environment_spec is not None:
            payload["environment_spec"] = environment_spec
        if compute_spec is not None:
            payload["compute_spec"] = compute_spec
        return self._parent._post(f"/v2/workspaces/{self._parent._workspace(workspace)}/environments", payload)

    def list(self, workspace: str | None = None) -> List[dict[str, Any]]:
        """List environments in *workspace*."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/environments")

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get an environment by name."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/environments/{name}")

    def delete(self, name: str, workspace: str | None = None) -> None:
        """Delete an environment by name."""
        self._parent._delete(f"/v2/workspaces/{self._parent._workspace(workspace)}/environments/{name}")


class _ComputeSpecResource:
    """AgentComputeSpec CRUD under ``nemo.agents.compute_specs``.

    A ComputeSpec is a reusable set of k8s-style resource requests/limits an
    invocation runs with.
    """

    def __init__(self, parent: AgentsResource) -> None:
        self._parent = parent

    def create(
        self,
        *,
        name: str,
        spec: ComputeSpecInline | dict[str, Any] | None = None,
        workspace: str | None = None,
        **spec_kwargs: Any,
    ) -> dict[str, Any]:
        """Create a compute spec.

        Args:
            name: Unique compute-spec name within the workspace.
            spec: The compute spec, as a shared :class:`ComputeSpecInline` model
                (the typed, discoverable path) or a plain dict. Only the fields
                explicitly set on the model are sent.
            workspace: Target workspace.
            **spec_kwargs: Back-compat loose ComputeSpecInline fields
                (``resources``, ``description``). Merged over ``spec`` when both
                are given. Prefer the typed ``spec=`` argument.

        Returns:
            The created AgentComputeSpec as a dict.
        """
        payload: dict[str, Any] = {**_spec_to_dict(spec), **spec_kwargs, "name": name}
        return self._parent._post(f"/v2/workspaces/{self._parent._workspace(workspace)}/compute-specs", payload)

    def list(self, workspace: str | None = None) -> List[dict[str, Any]]:
        """List compute specs in *workspace*."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/compute-specs")

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a compute spec by name."""
        return self._parent._get(f"/v2/workspaces/{self._parent._workspace(workspace)}/compute-specs/{name}")

    def delete(self, name: str, workspace: str | None = None) -> None:
        """Delete a compute spec by name."""
        self._parent._delete(f"/v2/workspaces/{self._parent._workspace(workspace)}/compute-specs/{name}")


# ----------------------------------------------------------------------
# Job sub-resources
# ----------------------------------------------------------------------
#
# Unlike the resources above, these route through the platform client's own
# request pipeline (``platform.post`` / ``platform.get``) rather than a bare
# ``httpx`` client, so the caller's auth headers, base URL, and retry policy
# are applied. A ``NemoJob`` subclass gets CLI and HTTP routes for free but no
# SDK surface, so each job collection needs a resource like this one.


def _execute_jobs_base(workspace: str) -> str:
    return f"/apis/agents/v2/workspaces/{workspace}/jobs/execute"


def _execute_job_body(
    spec: Mapping[str, Any],
    name: str | None,
    description: str | None,
) -> dict[str, Any]:
    """Build the create-job request body.

    ``name`` is omitted when not supplied so the Jobs service generates a
    unique one; sending a fixed name makes the second submission collide.
    """
    body: dict[str, Any] = {"spec": dict(spec)}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    return body


class _ExecuteJobsResource:
    """Sync ``client.agents.jobs.execute`` — the ``agents.execute`` job collection."""

    def __init__(self, platform: Any) -> None:
        self._platform = platform

    def create(
        self,
        *,
        spec: Mapping[str, Any],
        name: str | None = None,
        description: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Submit an execute-agent job. *spec* is an ``ExecuteAgentJobConfig``."""
        return self._platform.post(
            _execute_jobs_base(_resolve_workspace(self._platform, workspace)),
            body=_execute_job_body(spec, name, description),
            cast_to=dict[str, Any],
        )

    def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get one execute-agent job by name."""
        base = _execute_jobs_base(_resolve_workspace(self._platform, workspace))
        return self._platform.get(f"{base}/{name}", cast_to=dict[str, Any])

    def list_results(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """List the named results a finished execute-agent job saved."""
        base = _execute_jobs_base(_resolve_workspace(self._platform, workspace))
        return self._platform.get(f"{base}/{name}/results", cast_to=dict[str, Any])


class _AsyncExecuteJobsResource:
    """Async ``client.agents.jobs.execute``."""

    def __init__(self, platform: Any) -> None:
        self._platform = platform

    async def create(
        self,
        *,
        spec: Mapping[str, Any],
        name: str | None = None,
        description: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Submit an execute-agent job. *spec* is an ``ExecuteAgentJobConfig``."""
        return await self._platform.post(
            _execute_jobs_base(_resolve_workspace(self._platform, workspace)),
            body=_execute_job_body(spec, name, description),
            cast_to=dict[str, Any],
        )

    async def get(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """Get one execute-agent job by name."""
        base = _execute_jobs_base(_resolve_workspace(self._platform, workspace))
        return await self._platform.get(f"{base}/{name}", cast_to=dict[str, Any])

    async def list_results(self, name: str, workspace: str | None = None) -> dict[str, Any]:
        """List the named results a finished execute-agent job saved."""
        base = _execute_jobs_base(_resolve_workspace(self._platform, workspace))
        return await self._platform.get(f"{base}/{name}/results", cast_to=dict[str, Any])


class _JobsResource:
    """Sync ``client.agents.jobs`` namespace."""

    def __init__(self, platform: Any) -> None:
        self._platform = platform
        self._execute: _ExecuteJobsResource | None = None

    @property
    def execute(self) -> _ExecuteJobsResource:
        if self._execute is None:
            self._execute = _ExecuteJobsResource(self._platform)
        return self._execute


class _AsyncJobsResource:
    """Async ``client.agents.jobs`` namespace."""

    def __init__(self, platform: Any) -> None:
        self._platform = platform
        self._execute: _AsyncExecuteJobsResource | None = None

    @property
    def execute(self) -> _AsyncExecuteJobsResource:
        if self._execute is None:
            self._execute = _AsyncExecuteJobsResource(self._platform)
        return self._execute


class AsyncAgentsResource:
    """Async SDK namespace for ``nemo.agents.*``.

    Only ``jobs`` is implemented. Agent CRUD, deployments, and ``invoke``
    remain sync-only on :class:`AgentsResource`.
    """

    def __init__(self, platform: Any) -> None:
        self._platform = platform
        self._jobs: _AsyncJobsResource | None = None

    @property
    def jobs(self) -> _AsyncJobsResource:
        """Sub-resource for agents job collections."""
        if self._jobs is None:
            self._jobs = _AsyncJobsResource(self._platform)
        return self._jobs


agents_sdk_resources = NemoPluginSDKResources(
    sync_resource=AgentsResource,
    async_resource=AsyncAgentsResource,
)
