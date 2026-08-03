# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployment settings: which endpoint this install talks to, and with which models.

Separate from ``config.py`` for layering, not taste. ``config.py`` imports each
component's config slice from the component that owns it, and those components resolve
their models through ``components/model_config.py`` -- so anything ``model_config`` needs
has to sit *below* the components, and ``config.py`` sits above them. This module imports
nothing from the plugin.

For the run-parameter half of the configuration, and why the two do not share a
precedence rule, see ``config.py``.
"""

from typing import ClassVar

from nemo_platform_plugin.config import NemoConfig
from pydantic import BaseModel, Field, SecretStr

TIERS: tuple[str, ...] = ("smart", "mid", "fast")


class ModelsConfig(BaseModel):
    """Model name per tier.

    No tier has a default. A model name is only meaningful against a specific endpoint, so
    there is no portable value to fall back to, and failing at startup beats failing at the
    first LLM call minutes into a run.
    """

    smart: str | None = Field(default=None, description="Model for the smart tier, as your endpoint names it.")
    mid: str | None = Field(default=None, description="Model for the mid tier, as your endpoint names it.")
    fast: str | None = Field(default=None, description="Model for the fast tier, as your endpoint names it.")


class ExperimentalistConfig(NemoConfig):
    """Endpoint and model settings for this install.

    ``plugin_name`` gives this the ``NEMO_EXPERIMENTALIST_`` environment prefix and the
    ``experimentalist:`` section of the platform config file. Precedence is the platform's:
    environment, then config file, then these defaults. Nested fields use ``_``, so the
    smart tier is ``NEMO_EXPERIMENTALIST_MODELS_SMART``.

    Contrast :class:`~nemo_experimentalist_plugin.config.EvolutionaryOptimizerConfig`,
    which describes one experiment and takes no environment override at all.
    """

    plugin_name: ClassVar[str] = "experimentalist"
    plugin_description: ClassVar[str] = "Endpoint and model settings for the NeMo Experimentalist."

    api_base: str | None = Field(default=None, description="Base URL of the OpenAI-compatible endpoint.")
    api_key: SecretStr | None = Field(default=None, description="Credential for that endpoint.")
    models: ModelsConfig = Field(default_factory=ModelsConfig, description="Model name per tier.")
