# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Onboarding gate tool for the insights analyst agent.

On each conversation turn, this tool checks whether the user has been onboarded
(SOUL.md exists with content). If not, it returns the BOOTSTRAP.md template as
context so the agent knows to run the onboarding interview. If the user is already
onboarded, it returns the persisted SOUL.md and MEMORY.md as agent context.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from nat.builder.builder import Builder  # type: ignore[unresolved-import]
from nat.builder.function_info import FunctionInfo  # type: ignore[unresolved-import]
from nat.cli.register_workflow import register_function  # type: ignore[unresolved-import]
from nat.data_models.function import FunctionBaseConfig  # type: ignore[unresolved-import]

logger = logging.getLogger(__name__)

SOUL_FILENAME = "SOUL.md"
MEMORY_FILENAME = "MEMORY.md"
STATE_FILENAME = ".state.json"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class OnboardingGateConfig(FunctionBaseConfig, name="onboarding_gate"):
    """Configuration for the onboarding gate tool."""

    data_dir: str = "~/.nemo-insights"
    agent_name: str = ""
    agent_description: str = ""


def _resolve_user_dir(data_dir: str, user_id: str) -> Path:
    """Resolve the per-user data directory, expanding ~ and env vars."""
    base = Path(os.path.expandvars(os.path.expanduser(data_dir)))
    return base / user_id


def _is_onboarded(user_dir: Path) -> bool:
    """Check if onboarding is complete via state file or SOUL.md content."""
    state_file = user_dir / STATE_FILENAME
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            if state.get("onboarded_at"):
                return True
        except (json.JSONDecodeError, OSError):
            pass

    soul_file = user_dir / SOUL_FILENAME
    if soul_file.exists():
        content = soul_file.read_text().strip()
        return len(content) > 0

    return False


def _load_template(name: str) -> str:
    """Load a template file from the templates directory."""
    return (TEMPLATES_DIR / name).read_text()


def _load_role_definition() -> str:
    """Load the analyst agent's fixed role definition."""
    return _load_template("ANALYST_ROLE.md")


def _load_bootstrap_template() -> str:
    """Load the BOOTSTRAP.md onboarding interview template."""
    return _load_template("BOOTSTRAP.md")


def _build_known_context(config: OnboardingGateConfig) -> str:
    """Build a context block from platform-known agent metadata (if any)."""
    parts: list[str] = []
    if config.agent_name:
        parts.append(f"**Agent Name**: {config.agent_name}")
    if config.agent_description:
        parts.append(f"**Agent Description**: {config.agent_description}")

    if not parts:
        return ""

    return (
        "## Known Agent Metadata (from NeMo Platform)\n\n"
        "The following is already known about the Agent Under Test from its "
        "platform registration. Use this as a starting point — don't re-ask "
        "what's already here, but do probe deeper on anything underspecified.\n\n"
        + "\n".join(parts)
    )


def _load_persisted_context(user_dir: Path) -> str:
    """Load SOUL.md and MEMORY.md as combined agent context."""
    parts: list[str] = []

    soul_file = user_dir / SOUL_FILENAME
    if soul_file.exists():
        content = soul_file.read_text().strip()
        if content:
            parts.append(f"# Agent Under Test Description (SOUL.md)\n\n{content}")

    memory_file = user_dir / MEMORY_FILENAME
    if memory_file.exists():
        content = memory_file.read_text().strip()
        if content:
            parts.append(f"# Agent Memory (MEMORY.md)\n\n{content}")

    return "\n\n---\n\n".join(parts) if parts else ""


@register_function(config_type=OnboardingGateConfig)
async def onboarding_gate(config: OnboardingGateConfig, builder: Builder):
    """Tool that gates between onboarding and analyst modes.

    Always injects the analyst's fixed role definition. Then returns either
    the bootstrap template (if not onboarded) or the persisted SOUL.md +
    MEMORY.md context (if already onboarded).
    """

    async def _check_onboarding(user_id: str = "default") -> str:
        """Check onboarding status and return appropriate context.

        Args:
            user_id: Identifier for the user/workspace. Defaults to "default".

        Returns:
            The analyst role definition plus either onboarding instructions
            or the persisted agent context.
        """
        role = _load_role_definition()
        user_dir = _resolve_user_dir(config.data_dir, user_id)

        if _is_onboarded(user_dir):
            logger.info("User %s is onboarded, loading persisted context", user_id)
            context = _load_persisted_context(user_dir)
            if context:
                return (
                    f"{role}\n\n---\n\n"
                    "You are in ANALYST MODE. The following is your context about "
                    "the Agent Under Test. Use it to inform your analysis and "
                    f"recommendations.\n\n{context}"
                )
            return (
                f"{role}\n\n---\n\n"
                "User appears onboarded but no context files found. "
                "Ask if they'd like to re-run onboarding."
            )

        logger.info("User %s not onboarded, returning bootstrap template", user_id)
        template = _load_bootstrap_template()
        known_context = _build_known_context(config)
        known_section = f"\n\n{known_context}" if known_context else ""

        return (
            f"{role}\n\n---\n\n"
            "You are in ONBOARDING MODE. Follow the instructions below to interview "
            "the developer about their Agent Under Test. When you have gathered enough "
            "information, use the memory_writer tool to save SOUL.md and MEMORY.md.\n\n"
            f"{template}{known_section}"
        )

    yield FunctionInfo.from_fn(
        _check_onboarding,
        description=(
            "Check if the user has been onboarded. Returns the analyst role definition "
            "plus either onboarding instructions (if not yet onboarded) or the persisted "
            "agent context (if already onboarded). Call this at the start of each conversation."
        ),
    )
