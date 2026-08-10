# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract fixtures for submit-time RlJobInput JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_rl_plugin.schema import OutputRequest, RlJobInput

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize(
    "fixture_name",
    ["minimal_dpo.json", "integrations_wandb_mlflow.json"],
)
def test_contract_job_input_validates(fixture_name: str) -> None:
    path = FIXTURES_DIR / fixture_name
    spec = RlJobInput.model_validate(json.loads(path.read_text()))
    assert spec.training.type == "dpo"

    if spec.integrations is None:
        return

    assert spec.integrations.wandb is not None
    assert spec.integrations.wandb.project == "my-project"
    assert spec.integrations.wandb.name == "run-001"
    assert spec.integrations.wandb.api_key_secret is not None
    assert spec.integrations.wandb.api_key_secret.root == "default/wandb-api-key"
    assert spec.integrations.mlflow is not None
    assert spec.integrations.mlflow.tracking_uri == "http://mlflow:5000"
    assert spec.integrations.mlflow.name == "run-001"


def test_minimal_grpo_fixture_validates() -> None:
    path = FIXTURES_DIR / "minimal_grpo.json"
    spec = RlJobInput.model_validate(json.loads(path.read_text()))
    assert spec.training.type == "grpo"
    assert spec.environment == "default/ascii-tree-env"
    assert spec.training.num_generations_per_prompt == 4
    assert spec.training.finetuning_type == "all_weights"


def test_minimal_grpo_lora_fixture_validates() -> None:
    path = FIXTURES_DIR / "minimal_grpo_lora.json"
    spec = RlJobInput.model_validate(json.loads(path.read_text()))
    assert spec.training.type == "grpo"
    assert spec.training.finetuning_type == "lora"
    assert spec.training.lora is not None
    assert spec.training.lora.rank == 32
    assert spec.training.lora.alpha == 32
    assert spec.environment == "default/ascii-tree-env"


def test_output_name_cannot_exceed_response_limit() -> None:
    assert len(OutputRequest(name="x" * 255).name or "") == 255
    with pytest.raises(ValueError):
        OutputRequest(name="x" * 256)
