# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare Platform-owned environment paths before Fabric runtime startup."""

import logging
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nemo_agents_plugin.agent_config import AgentConfig

logger = logging.getLogger(__name__)

#: Prefix for the directory an agent tree is copied to when its mounted location
#: cannot be written to.
RUNTIME_BASE_DIR_PREFIX = "nemo-agent-runtime"


@dataclass(frozen=True, slots=True)
class RuntimeBaseDir:
    """An agent root the runtime can write to, and whether this process created it."""

    path: Path
    staged: bool


def resolve_runtime_base_dir(config_path: Path) -> RuntimeBaseDir:
    """Return an agent root the runtime can write to, copying the tree out if it cannot.

    Fabric resolves everything against the agent root — skills and prompts to
    read, but also the workspace and artifacts to write. In k8s the agent config
    arrives on a read-only ConfigMap ``subPath`` whose parent kubelet creates as
    root, so the runtime user can read its agent but cannot create anything
    beside it. Docker has no such mount and is unaffected.

    A staged copy belongs to one process lifecycle: it goes to a fresh directory
    and :func:`release_runtime_base_dir` removes it at shutdown, so a later
    runtime can never read skills or prompts left behind by an earlier one. The
    tree is bounded by the spec-fileset staging limits, so copying it is cheap
    next to starting a runtime.
    """
    source = config_path.parent
    if os.access(source, os.W_OK):
        return RuntimeBaseDir(path=source, staged=False)

    target = Path(tempfile.mkdtemp(prefix=f"{RUNTIME_BASE_DIR_PREFIX}-"))
    logger.info("Agent root %s is not writable; staging it to %s for the runtime.", source, target)
    shutil.copytree(source, target, dirs_exist_ok=True)
    # copytree carries the source's mode across, so the copy of a read-only mount
    # is read-only too — restore write access on the directories we just made.
    for directory in (target, *(path for path in target.rglob("*") if path.is_dir())):
        directory.chmod(directory.stat().st_mode | stat.S_IRWXU)
    return RuntimeBaseDir(path=target, staged=True)


def release_runtime_base_dir(base_dir: RuntimeBaseDir) -> None:
    """Remove a staged agent root. A root used in place is left alone."""
    if not base_dir.staged:
        return
    shutil.rmtree(base_dir.path, ignore_errors=True)
    logger.info("Removed staged agent root %s.", base_dir.path)


def ensure_local_workspace_dir(agent_config: AgentConfig, base_dir: Path) -> None:
    """Create the configured local workspace relative to the agent base directory."""
    if agent_config.environment.provider != "local":
        return

    configured_workspace = Path(agent_config.environment.workspace)
    if configured_workspace.is_absolute():
        raise ValueError("Local workspace path must be relative to the agent base directory.")

    resolved_base_dir = base_dir.resolve()
    workspace = (resolved_base_dir / configured_workspace).resolve()
    if not workspace.is_relative_to(resolved_base_dir):
        raise ValueError("Local workspace path must remain within the agent base directory.")

    workspace.mkdir(parents=True, exist_ok=True)
