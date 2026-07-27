# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal backend for standalone Eval Author runs.

Replicates the ``get_insight`` and ``get_agent_code`` behavior from
``LocalExperimentalistBackend`` so ``run_eval_author`` does not depend on
Experimentalist.

TODO(shared-module): unify agent materialization with Experimentalist backend.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import httpx
from nemo_eval_author_plugin.repository import (
    AgentSource,
    clone_agent_repo,
    looks_like_git,
    split_agent_spec,
    split_git_ref,
)
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform

_ModelT = TypeVar("_ModelT")

_AGENT_COPY_EXCLUDE_NAMES = {
    ".git",
    ".venv",
    "artifacts",
    "dataset",
    "eval-and-optimize",
    "scratch",
}


def _ignore_agent_copy(directory: str, contents: list[str]) -> set[str]:
    del directory
    return {name for name in contents if name in _AGENT_COPY_EXCLUDE_NAMES}


def _load_entity(cls: type[_ModelT], path: Path) -> _ModelT:
    """Deserialize *path* as JSON into *cls*, restoring the private ``_id`` field."""
    data = json.loads(path.read_text())
    entity_id = data.get("id", "")
    obj = cls.model_validate(data)
    if entity_id:
        cast(Any, obj)._id = entity_id
    return obj


class EvalAuthorBackend:
    """Insight and agent-code materialization for Eval Author runs."""

    def __init__(self, *, client: AsyncNeMoPlatform | None, path: Path) -> None:
        self.client = client
        self.path = path

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        p = Path(insight_id)
        if p.exists():
            return _load_entity(Insight, p)
        if self.client is None:
            raise ValueError(
                f"Insight {insight_id!r} is not an existing local file and no platform "
                "client is available to fetch it from the platform."
            )
        try:
            return await self.client.insights.insights.get(workspace=workspace, insight_id=insight_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError(f"Insight not found on the platform: {insight_id!r}") from exc
            raise ValueError(f"Failed to fetch insight {insight_id!r} from the platform: {exc}") from exc

    async def get_agent_code(
        self, *, workspace: str, agent: str | Path, dest: Path, clone_depth: int | None = None
    ) -> AgentSource | None:
        del workspace
        if looks_like_git(str(agent)):
            return await self._clone_git_agent(str(agent), dest, clone_depth=clone_depth)
        src = Path(agent)
        if not src.exists():
            raise FileNotFoundError(f"Local agent path not found: {src}")
        if dest.resolve() != src.resolve():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=_ignore_agent_copy)
        return None

    async def _clone_git_agent(self, agent: str, dest: Path, *, clone_depth: int | None = None) -> AgentSource:
        try:
            return await asyncio.to_thread(clone_agent_repo, agent, dest, clone_depth=clone_depth)
        except subprocess.CalledProcessError:
            remote, _ = split_git_ref(split_agent_spec(agent)[0])
            from nemo_eval_author_plugin.repository import _redact_url

            raise ValueError(f"failed to fetch --agent {_redact_url(remote)!r}") from None


def make_eval_author_backend(
    *,
    client: AsyncNeMoPlatform | None,
    experiments_output: str,
    mode: Literal["local", "remote"],
) -> EvalAuthorBackend:
    """Select the Eval Author backend for *mode*.

    Both local and remote modes use the same insight/agent materialization
    implementation; remote mode requires a platform client for platform-backed
    insight ids.
    """
    if client is None and mode == "remote":
        raise ValueError("remote Eval Author backend requires a platform client")
    return EvalAuthorBackend(client=client, path=Path(experiments_output))
