# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""User-selectable model configuration for a war-game.

Iron Swarm's five model-driven roles collapse into three user-facing groups:

- ``attack``   — garak's red-team + detector models (the adversary).
- ``analysis`` — the defenders + the benign validator (both its synth suite-generation and its judge)
  — one shared "analysis" model.
- ``agent``    — the victim agent's own LLM (an optional override of what its workflow declares).

Each group is a :class:`ModelChoice` (model name, optional custom ``base_url``, optional Secrets
name for a custom provider key). ``None`` anywhere means "use the built-in default", so an unset
config reproduces today's behavior exactly.

This module is the single source of truth shared by the entity (stored default), the job spec
(per-run override), and the API (the defaults the UI pre-fills). It imports nothing plugin-internal
so it can be depended on from anywhere without cycles.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Built-in defaults, mirrored from iron-swarm's own literals so the UI can present them pre-filled.
# attack → iron_swarm.agents.attackers.agent_breaker.config; analysis → iron_swarm.llm.
ATTACK_DEFAULT_MODEL = "aws/anthropic/claude-opus-4-5"
ATTACK_DEFAULT_BASE_URL = "https://inference-api.nvidia.com/v1/"
ANALYSIS_DEFAULT_MODEL = "nvidia/nvidia/Nemotron-3-Nano-30B-A3B"
ANALYSIS_DEFAULT_BASE_URL = "https://inference-api.nvidia.com/v1"


class ModelChoice(BaseModel):
    """One group's model selection. Every field is optional; ``None`` → the group's built-in default."""

    model: str | None = Field(default=None, description="Model name/URN; null uses the group default.")
    base_url: str | None = Field(default=None, description="Custom OpenAI-compatible endpoint; null uses the default.")
    api_key_secret: str | None = Field(
        default=None,
        description="Name of a NeMo Secret holding the provider API key for a custom endpoint; null uses the "
        "platform's provisioned iron-swarm inference key.",
    )


class WarGameModels(BaseModel):
    """The three model groups for a war-game. An unset group uses iron-swarm's built-in default."""

    attack: ModelChoice | None = Field(default=None, description="garak red-team + detector model.")
    analysis: ModelChoice | None = Field(
        default=None, description="Defenders + benign validator (synth suite-generation + judge) model."
    )
    agent: ModelChoice | None = Field(default=None, description="Victim agent LLM override (model only).")


class ModelGroupDefault(BaseModel):
    """The default model + endpoint the UI shows for one group."""

    model: str
    base_url: str


class ModelConfigDefaults(BaseModel):
    """Defaults surfaced to the UI so pickers pre-fill without hardcoding iron-swarm's literals."""

    attack: ModelGroupDefault
    analysis: ModelGroupDefault


def model_config_defaults() -> ModelConfigDefaults:
    """Return the built-in per-group model defaults (the values shown pre-filled in the UI)."""
    return ModelConfigDefaults(
        attack=ModelGroupDefault(model=ATTACK_DEFAULT_MODEL, base_url=ATTACK_DEFAULT_BASE_URL),
        analysis=ModelGroupDefault(model=ANALYSIS_DEFAULT_MODEL, base_url=ANALYSIS_DEFAULT_BASE_URL),
    )
