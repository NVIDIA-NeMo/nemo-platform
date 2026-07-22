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

    # Invocation (routes through the agents gateway)
    result = nemo.agents.invoke(agent="calculator", input="What is 2+2?")
"""

from __future__ import annotations

import re
from typing import Any, List

import httpx
from nemo_platform_plugin.sdk import NemoPluginSDKResources

_DEFAULT_WORKSPACE = "default"
_DEFAULT_TIMEOUT = 30
_DEFAULT_MODEL_PLACEHOLDER = re.compile(r"\$(?:\{NEMO_DEFAULT_MODEL\}|NEMO_DEFAULT_MODEL(?![A-Za-z0-9_]))")


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
        """
        self._platform = platform
        self._deployments: _DeploymentResource | None = None

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
    def deployments(self) -> "_DeploymentResource":
        """Sub-resource for deployment lifecycle operations."""
        if self._deployments is None:
            self._deployments = _DeploymentResource(self)
        return self._deployments

    # ------------------------------------------------------------------
    # Invocation and evaluation
    # ------------------------------------------------------------------

    def invoke(
        self,
        *,
        input: str,
        agent: str | None = None,
        deployment: str | None = None,
        workspace: str | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """Send a single request to an agent via the gateway.

        Args:
            input: The user message / query string.
            agent: Agent name (gateway resolves the active deployment).
            deployment: Deployment name (direct targeting).
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

        payload = {
            "messages": [{"role": "user", "content": input}],
            "stream": False,
        }
        return self._post(path, payload, timeout=timeout)

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
        return workspace or getattr(self._platform, "workspace", None) or _DEFAULT_WORKSPACE

    def _agents_url(self, path: str) -> str:
        return self._base_url() + "/apis/agents" + path

    def _get(self, path: str) -> Any:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.get(self._agents_url(path))
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, payload: dict[str, Any], timeout: int = _DEFAULT_TIMEOUT) -> dict[str, Any]:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._agents_url(path), json=payload)
            resp.raise_for_status()
            return resp.json()

    def _delete(self, path: str) -> None:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.delete(self._agents_url(path))
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
            workspace: Target workspace.

        Returns:
            The created deployment as a dict.
        """
        if image and deployment_mode == "subprocess":
            raise ValueError("image requires deployment_mode='docker' or 'k8s'.")
        payload: dict[str, Any] = {"agent": agent, "deployment_mode": deployment_mode}
        if name:
            payload["name"] = name
        if image:
            payload["image"] = image
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


agents_sdk_resources = NemoPluginSDKResources(sync_resource=AgentsResource)
