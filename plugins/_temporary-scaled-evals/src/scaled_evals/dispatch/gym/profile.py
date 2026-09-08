# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Materialize validated, non-secret Gym framework profiles for the harness."""

from __future__ import annotations

import json
from typing import Any

from scaled_evals.models.gym_profile import validate_gym_profile_config


def gym_profile_env(raw_config: dict[str, Any]) -> dict[str, str]:
    """Translate a validated canonical profile into the existing harness interface."""
    profile = validate_gym_profile_config(raw_config)
    env = {
        "GYM_COMMAND": profile.command,
        "GYM_CONFIG_PATHS": ",".join(profile.config_paths),
        "GYM_AGENT_NAME": profile.agent_name,
    }
    if profile.input_jsonl_fpath:
        env["GYM_INPUT_JSONL"] = profile.input_jsonl_fpath
    if profile.split:
        env["GYM_SPLIT"] = profile.split
    if profile.limit is not None:
        env["GYM_LIMIT"] = str(profile.limit)

    overrides: list[str] = []
    if profile.command == "run_and_collect" and profile.limit is not None:
        overrides.append(f"++limit={profile.limit}")
    if profile.num_repeats is not None:
        overrides.append(f"++num_repeats={profile.num_repeats}")
    if profile.num_samples_in_parallel is not None:
        overrides.append(f"++num_samples_in_parallel={profile.num_samples_in_parallel}")
    overrides.extend(
        f"++responses_create_params.{key}={_hydra_value(value)}"
        for key, value in sorted(profile.responses_create_params.items())
    )
    overrides.extend(f"++{key}={_hydra_value(value)}" for key, value in sorted(profile.overrides.items()))
    if overrides:
        env["GYM_EXTRA_OVERRIDES"] = ",".join(overrides)
    return env


def _hydra_value(value: bool | float | int | str) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return json.dumps(value) if any(ch.isspace() for ch in value) else value
    return str(value)
