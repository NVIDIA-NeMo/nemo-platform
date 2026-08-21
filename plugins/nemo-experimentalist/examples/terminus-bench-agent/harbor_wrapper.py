# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist-only entrypoint for a staged Harbor candidate checkout."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from harbor.models.trial.result import AgentInfo as HostAgentInfo

_SOURCE_ROOT = Path(__file__).resolve().parent / "src"


def _is_harbor_module(name: str) -> bool:
    return name == "harbor" or name.startswith("harbor.")


def _load_candidate_harbor_types() -> tuple[Any, Any, Any]:
    """Load Terminus-2 from this candidate without replacing host Harbor modules."""
    host_modules = {name: module for name, module in sys.modules.items() if _is_harbor_module(name)}
    for name in host_modules:
        sys.modules.pop(name, None)

    source_root = str(_SOURCE_ROOT)
    inserted_path = source_root not in sys.path
    if inserted_path:
        sys.path.insert(0, source_root)
    importlib.invalidate_caches()
    try:
        terminus_module = importlib.import_module("harbor.agents.terminus_2.terminus_2")
        terminus_path = Path(terminus_module.__file__).resolve()
        if not terminus_path.is_relative_to(_SOURCE_ROOT.resolve()):
            raise RuntimeError(f"Terminus-2 resolved outside the Experimentalist candidate: {terminus_path}")
        environment_module = importlib.import_module("harbor.environments.base")
        context_module = importlib.import_module("harbor.models.agent.context")
        return (
            terminus_module.Terminus2,
            environment_module.BaseEnvironment,
            context_module.AgentContext,
        )
    finally:
        for name in list(sys.modules):
            if _is_harbor_module(name):
                sys.modules.pop(name, None)
        sys.modules.update(host_modules)
        if inserted_path:
            sys.path.remove(source_root)


if TYPE_CHECKING:
    from harbor.agents.terminus_2.terminus_2 import Terminus2 as CandidateTerminus2
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
else:
    CandidateTerminus2, BaseEnvironment, AgentContext = _load_candidate_harbor_types()

MODEL_NAME = "openai/azure/anthropic/claude-opus-4-8"
API_BASE = "https://inference-api.nvidia.com/v1"
MAX_TURNS = 60


class WrappedAgent(CandidateTerminus2):
    """Terminus-2 configured for this Experimentalist benchmark."""

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        api_base: str | None = None,
        stream: bool = True,
        max_turns: int = MAX_TURNS,
        llm_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_llm_kwargs = dict(llm_kwargs or {})
        if inference_api_key := os.environ.get("INFERENCE_API_KEY"):
            resolved_llm_kwargs.setdefault("api_key", inference_api_key)
        super().__init__(
            logs_dir=logs_dir,
            model_name=model_name or MODEL_NAME,
            api_base=api_base or API_BASE,
            stream=stream,
            max_turns=max_turns,
            llm_kwargs=resolved_llm_kwargs,
            **kwargs,
        )

    @override
    def to_agent_info(self) -> HostAgentInfo:
        """Normalize candidate metadata to the Harbor model used by the runner."""
        candidate_info = super().to_agent_info()
        return HostAgentInfo.model_validate(candidate_info.model_dump())

    async def _publish_atif_artifact(self, environment: BaseEnvironment) -> None:
        trajectory = self.logs_dir / "trajectory.json"
        if not trajectory.is_file():
            return
        try:
            result = await environment.exec("mkdir -p /app/traces")
            if result.return_code != 0:
                self.logger.warning("Could not create /app/traces for the Experimentalist ATIF artifact")
                return
            await environment.upload_file(trajectory, "/app/traces/trajectory.atif.json")
        except Exception:
            self.logger.warning("Could not publish the Experimentalist ATIF artifact", exc_info=True)

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        try:
            await super().run(instruction, environment, context)
        finally:
            await self._publish_atif_artifact(environment)
