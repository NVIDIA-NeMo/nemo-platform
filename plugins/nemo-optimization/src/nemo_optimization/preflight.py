# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pre-flight checks before dispatching an optimize study."""

from __future__ import annotations

import logging
import re
from typing import Any

from nemo_platform import NeMoPlatform, NotFoundError

logger = logging.getLogger(__name__)

_IGW_LLM_TYPES = frozenset({"openai", "nim", "azure_openai"})
_UNEXPANDED_ENV_VAR_RE = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def preflight_validate_llm_models(
    optimize_config: dict[str, Any],
    *,
    workspace: str,
    sdk: NeMoPlatform | None,
    agent_config: dict[str, Any] | None = None,
) -> None:
    """Validate IGW-routed LLM model names against workspace VirtualModels."""
    if sdk is None:
        return

    llms: dict[str, Any] = {}
    if isinstance(agent_config, dict) and isinstance(agent_config.get("llms"), dict):
        llms.update(agent_config["llms"])
    if isinstance(optimize_config.get("llms"), dict):
        llms.update(optimize_config["llms"])
    if not llms:
        return

    to_check: dict[str, str] = {}
    for llm_key, llm_cfg in llms.items():
        if not isinstance(llm_cfg, dict):
            continue
        if llm_cfg.get("_type") not in _IGW_LLM_TYPES:
            continue
        model_name = llm_cfg.get("model_name")
        if not isinstance(model_name, str) or not model_name:
            continue
        if _UNEXPANDED_ENV_VAR_RE.search(model_name):
            continue
        to_check.setdefault(model_name, llm_key)

    if not to_check:
        return

    missing: list[tuple[str, str]] = []
    for model_name, llm_key in to_check.items():
        try:
            sdk.inference.virtual_models.retrieve(name=model_name, workspace=workspace)
        except NotFoundError:
            missing.append((model_name, llm_key))
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Could not validate LLM %r (model_name=%r) in workspace %r: %s",
                llm_key,
                model_name,
                workspace,
                exc,
                exc_info=exc,
            )

    if missing:
        details = ", ".join(f"{name!r} (llms.{key}.model_name)" for name, key in missing)
        raise ValueError(
            f"The following LLM model(s) are not registered as VirtualModels in workspace "
            f"{workspace!r}: {details}."
        )
