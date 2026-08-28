# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor 0.20 adapter for the rho-agent fixture's pinned source revision."""

from __future__ import annotations

import base64
import os
import shlex
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

RHO_REVISION = "04b9cfa1c940e8c3fd6ecdd6888f9fabd0110558"
RHO_AGENT_ROOT = "/rho-agent"
RHO_AGENT_VENV_PYTHON = f"{RHO_AGENT_ROOT}/.venv/bin/python"

# Defaults match plugins/nemo-eval-author/walkthrough/env (this file is copied into workspaces).
DEFAULT_INFERENCE_BASE_URL = "https://inference-api.nvidia.com/v1"
# LiteLLM routes OpenAI-compatible gateways via the openai/ provider prefix.
DEFAULT_RHO_AGENT_MODEL = "openai/nvidia/qwen/qwen3.5-122b-a10b"

_LITELLM_PROVIDER_PREFIXES = frozenset(
    {
        "openai",
        "anthropic",
        "azure",
        "bedrock",
        "cohere",
        "gemini",
        "huggingface",
        "mistral",
        "ollama",
        "vertex_ai",
    }
)


def litellm_model_for_openai_compatible_gateway(model: str) -> str:
    """Return a LiteLLM model string for NVIDIA inference-api style model IDs."""
    trimmed = model.strip()
    if not trimmed:
        return trimmed
    prefix = trimmed.split("/", 1)[0]
    if prefix in _LITELLM_PROVIDER_PREFIXES:
        return trimmed
    return f"openai/{trimmed}"


class RhoAgent(BaseAgent):
    """Run pinned rho-agent from a pre-baked task image using Harbor's BaseAgent API."""

    SUPPORTS_ATIF = True

    @staticmethod
    def name() -> str:
        return "rho-agent"

    def version(self) -> str:
        return RHO_REVISION

    async def setup(self, environment: BaseEnvironment) -> None:
        probe = await environment.exec(
            command=f"test -x {shlex.quote(RHO_AGENT_VENV_PYTHON)}",
            timeout_sec=30,
        )
        if probe.return_code == 0:
            await self._ensure_atif_compat(environment)
            return

        if os.environ.get("RHO_HARBOR_ALLOW_RUNTIME_INSTALL") == "1":
            await self._runtime_install(environment)
            return

        raise RuntimeError(
            "rho-agent is not present in the task image. Build the walkthrough image "
            "with plugins/nemo-eval-author/walkthrough/rho-agent/build_agent_image.sh "
            "and use a task Dockerfile that starts `FROM nemo-eval-author/rho-agent-harbor:<tag>`. "
            "Set RHO_HARBOR_ALLOW_RUNTIME_INSTALL=1 only for legacy unrestricted trials."
        )

    async def _ensure_atif_compat(self, environment: BaseEnvironment) -> None:
        target = f"{RHO_AGENT_ROOT}/rho_atif_compat.py"
        probe = await environment.exec(command=f"test -f {shlex.quote(target)}", timeout_sec=15)
        if probe.return_code == 0:
            return

        converter = Path(__file__).with_name("rho_atif_compat.py").read_bytes()
        encoded = base64.b64encode(converter).decode()
        result = await environment.exec(
            command=(f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(target)}"),
            user="root",
        )
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout)

    async def _runtime_install(self, environment: BaseEnvironment) -> None:
        command = (
            "apt-get update && "
            "apt-get install -y curl git python3 python3-venv && "
            "curl -LsSf https://astral.sh/uv/install.sh | sh && "
            'export PATH="$HOME/.local/bin:$PATH" && '
            "git clone https://github.com/smith-nathanh/rho-agent.git /rho-agent && "
            f"git -C /rho-agent checkout {RHO_REVISION} && "
            "cd /rho-agent && uv sync --frozen --extra evals"
        )
        result = await environment.exec(command=command, user="root", timeout_sec=300)
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout)
        await self._ensure_atif_compat(environment)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_INFERENCE_BASE_URL)
        raw_model = os.environ.get("RHO_AGENT_MODEL") or self.model_name or DEFAULT_RHO_AGENT_MODEL
        model = litellm_model_for_openai_compatible_gateway(raw_model)
        env = {
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
            "OPENAI_API_BASE": base_url,
            "OPENAI_BASE_URL": base_url,
            "RHO_AGENT_MODEL": model,
            "RHO_AGENT_TELEMETRY_DB": "/logs/agent/telemetry.db",
            "RHO_AGENT_CONFIRM_DONE": "0",
            "RHO_AGENT_TEMPERATURE": "0",
        }
        command = (
            "set -o pipefail; "
            f"{RHO_AGENT_VENV_PYTHON} -B -m rho_agent.eval.harbor.runner "
            f"{shlex.quote(instruction)} "
            f"{shlex.quote('/app')} "
            "2>&1 | tee /logs/agent/stdout.txt && "
            f"{RHO_AGENT_VENV_PYTHON} {RHO_AGENT_ROOT}/rho_atif_compat.py "
            "/logs/agent/trajectory.json"
        )
        result = await environment.exec(command=f"bash -c {shlex.quote(command)}", env=env)
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout)


__all__ = ["RhoAgent", "litellm_model_for_openai_compatible_gateway"]
