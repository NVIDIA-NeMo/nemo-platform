# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Memory writer tool for persisting SOUL.md and MEMORY.md files.

The analyst agent calls this tool to write onboarding discoveries and ongoing
context to the filesystem. On first successful write of SOUL.md, the tool marks
the user as onboarded via a .state.json sidecar file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from nat.builder.builder import Builder  # type: ignore[unresolved-import]
from nat.builder.function_info import FunctionInfo  # type: ignore[unresolved-import]
from nat.cli.register_workflow import register_function  # type: ignore[unresolved-import]
from nat.data_models.function import FunctionBaseConfig  # type: ignore[unresolved-import]

logger = logging.getLogger(__name__)

SOUL_FILENAME = "SOUL.md"
MEMORY_FILENAME = "MEMORY.md"
STATE_FILENAME = ".state.json"

MAX_SOUL_BYTES = 4096
MAX_MEMORY_BYTES = 8192


class MemoryWriterConfig(FunctionBaseConfig, name="memory_writer"):
    """Configuration for the memory writer tool."""

    data_dir: str = "~/.nemo-insights"


def _resolve_user_dir(data_dir: str, user_id: str) -> Path:
    """Resolve the per-user data directory, expanding ~ and env vars."""
    base = Path(os.path.expandvars(os.path.expanduser(data_dir)))
    return base / user_id


def _read_state(user_dir: Path) -> dict:
    """Read the .state.json sidecar, returning empty dict if missing/corrupt."""
    state_file = user_dir / STATE_FILENAME
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_state(user_dir: Path, state: dict) -> None:
    """Persist state to .state.json."""
    state_file = user_dir / STATE_FILENAME
    state_file.write_text(json.dumps(state, indent=2))


@register_function(config_type=MemoryWriterConfig)
async def memory_writer(config: MemoryWriterConfig, builder: Builder):
    """Tool for the agent to persist SOUL.md and MEMORY.md files."""

    async def write_soul(user_id: str, content: str) -> str:
        """Write or overwrite the SOUL.md file for a user.

        SOUL.md contains the stable description of the Agent Under Test:
        purpose, domain, success criteria, feedback signals, and optimization scope.

        Args:
            user_id: Identifier for the user/workspace. Use "default" if unknown.
            content: The full markdown content to write to SOUL.md.

        Returns:
            Confirmation message or error description.
        """
        if not content or not content.strip():
            return "Error: content cannot be empty."

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_SOUL_BYTES:
            return (
                f"Error: content exceeds maximum size of {MAX_SOUL_BYTES} bytes "
                f"({len(content_bytes)} bytes provided). Please condense."
            )

        user_dir = _resolve_user_dir(config.data_dir, user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        soul_file = user_dir / SOUL_FILENAME
        soul_file.write_text(content)
        logger.info("Wrote SOUL.md for user %s (%d bytes)", user_id, len(content_bytes))

        state = _read_state(user_dir)
        if not state.get("onboarded_at"):
            state["onboarded_at"] = datetime.now(timezone.utc).isoformat()
            state["onboarded_version"] = "1"
            _write_state(user_dir, state)
            logger.info("Marked user %s as onboarded", user_id)

        return f"Successfully wrote SOUL.md ({len(content_bytes)} bytes). User is now onboarded."

    async def write_memory(user_id: str, content: str) -> str:
        """Write or overwrite the MEMORY.md file for a user.

        MEMORY.md contains specific facts about the AUT's current state:
        model in use, known pain points, constraints, eval dataset locations, etc.

        Args:
            user_id: Identifier for the user/workspace. Use "default" if unknown.
            content: The full markdown content to write to MEMORY.md.

        Returns:
            Confirmation message or error description.
        """
        if not content or not content.strip():
            return "Error: content cannot be empty."

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_MEMORY_BYTES:
            return (
                f"Error: content exceeds maximum size of {MAX_MEMORY_BYTES} bytes "
                f"({len(content_bytes)} bytes provided). Please condense."
            )

        user_dir = _resolve_user_dir(config.data_dir, user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        memory_file = user_dir / MEMORY_FILENAME
        memory_file.write_text(content)
        logger.info("Wrote MEMORY.md for user %s (%d bytes)", user_id, len(content_bytes))

        return f"Successfully wrote MEMORY.md ({len(content_bytes)} bytes)."

    yield FunctionInfo.from_fn(
        write_soul,
        description=(
            "Write the SOUL.md file for a user. This contains the stable description "
            "of the Agent Under Test: its purpose, domain, users, success criteria, "
            "feedback signals, and optimization scope. Call this after the onboarding "
            "interview to persist what you learned."
        ),
    )

    yield FunctionInfo.from_fn(
        write_memory,
        description=(
            "Write the MEMORY.md file for a user. This contains specific facts about "
            "the AUT's current state: model in use, known pain points, optimization "
            "constraints, eval dataset locations, and other concrete details."
        ),
    )
