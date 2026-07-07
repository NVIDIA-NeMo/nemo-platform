# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric agent-eval runtime: config shapes for different harnesses.

The same :class:`~nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime.FabricAgentRuntime` targets
different agent harnesses purely via the Fabric config — the harness is selected by its
``harness.adapter_id``, never inferred from a model. Across harnesses the shape differs mainly in that
``adapter_id``, ``runtime.transport``, and any harness-specific ``harness.settings``:

* **Codex CLI** (``nvidia.fabric.codex.cli``) runs the agent as a subprocess — ``transport="cli"`` —
  and takes codex-specific ``harness.settings`` (sandbox mode, git-repo check, ...).
* **Hermes SDK** (``nvidia.fabric.hermes.sdk``) runs in-library — ``transport="library"`` — and
  declares its ``input``/``output`` schemas instead.

An optional ``model=`` slug (e.g. ``"openai/gpt-5.4"``) can be passed to ``FabricAgentRuntime`` to
overlay the model as a final profile, mirroring Fabric's own Harbor integration.

The configs are built from ``nemo_fabric``'s typed config objects (``FabricConfig`` etc.), which
validate structure at construction. That makes this module — like any real Fabric use — require the
optional native stack (``nemo-fabric[codex,relay]`` + the ``nemo-relay`` gateway, plus the ``codex``
CLI for the Codex harness); see ``script/dev-install-fabric.sh``. Run it (``python -m ...`` or
directly) to print each harness config.
"""

from __future__ import annotations

import json

from nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime import FabricAgentRuntime
from nemo_fabric import (  # ty: ignore[unresolved-import]
    FabricConfig,
    HarnessConfig,
    MetadataConfig,
    RuntimeConfig,
)

#: Codex CLI harness — subprocess transport, codex-specific harness settings.
CODEX_CLI_CONFIG = FabricConfig(
    metadata=MetadataConfig(name="codex-eval"),
    harness=HarnessConfig(
        adapter_id="nvidia.fabric.codex.cli",
        settings={"sandbox": "read-only", "skip_git_repo_check": True},
    ),
    models={"default": {"provider": "openai", "model": "gpt-5.4"}},
    runtime=RuntimeConfig(mode="oneshot", transport="cli"),
)

#: Hermes SDK harness — in-library transport, explicit chat/message schemas.
HERMES_SDK_CONFIG = FabricConfig(
    metadata=MetadataConfig(name="hermes-eval"),
    harness=HarnessConfig(adapter_id="nvidia.fabric.hermes.sdk", resolution="preinstalled"),
    models={"default": {"provider": "nvidia", "model": "qwen2.5-coder-32b"}},
    runtime=RuntimeConfig(mode="oneshot", transport="library", input_schema="chat", output_schema="message"),
)

#: Named Fabric configs, one per harness, keyed by a short label.
HARNESS_CONFIGS: dict[str, FabricConfig] = {
    "codex-cli": CODEX_CLI_CONFIG,
    "hermes-sdk": HERMES_SDK_CONFIG,
}


def build_runtime(harness: str, *, model: str | None = None, work_root: str | None = None) -> FabricAgentRuntime:
    """Build a :class:`FabricAgentRuntime` for a named harness (see :data:`HARNESS_CONFIGS`)."""
    return FabricAgentRuntime(config=HARNESS_CONFIGS[harness], model=model, work_root=work_root)


def main() -> None:
    """Print each harness's Fabric config to show how the structure differs."""
    for harness, config in HARNESS_CONFIGS.items():
        build_runtime(harness)  # verify the config constructs a runtime
        print(f"# {harness}  (adapter_id={config.harness.adapter_id})")
        print(json.dumps(config.to_mapping(), indent=2))
        print()


if __name__ == "__main__":
    main()
