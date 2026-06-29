# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract fixtures for submit-time RlJobInput JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_rl_plugin.schema import RlJobInput

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
