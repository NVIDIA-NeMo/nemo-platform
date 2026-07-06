# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU e2e: automodel SFT on SQuAD — LoRA and full-weight, with uplift eval.

Flow per case: prepare SQuAD CHAT data → register base entity → submit an
``automodel`` SFT job → deploy on vLLM → deterministic base-vs-tuned uplift (F1 on
gold answer spans).

- **LoRA** (``finetuning_type='lora'``): the completed job auto-registers its
  adapter on the base entity, which hot-reloads onto a single ``lora_enabled``
  deployment. Base and adapter are evaluated on that one deployment.
- **Full weight** (``finetuning_type='all_weights'``): the job registers a new
  output entity; base and tuned entities are deployed and evaluated separately.
"""

from __future__ import annotations

import logging

import pytest
from nemo_automodel_plugin.schema import AutomodelJobInput
from nemo_platform import NeMoPlatform
from nmp.testing.e2e import customizer as cust
from nmp.testing.e2e import customizer_datasets as cds
from nmp.testing.e2e import customizer_eval as ceval

logger = logging.getLogger(__name__)

BASE_MODEL_HF = "Qwen/Qwen3-0.6B"
BASE_ENTITY = "qwen3-0-6b-automodel"


@pytest.fixture(scope="module")
def squad_fileset(sdk: NeMoPlatform, customizer_workspace: str, squad_local: tuple) -> str:
    """Upload SQuAD train/val JSONL to one dataset fileset (shared across cases)."""
    train_path, val_path = squad_local
    name = cust.get_unique_name("squad")
    cds.create_dataset_fileset(
        sdk,
        customizer_workspace,
        name,
        {"train.jsonl": train_path, "validation.jsonl": val_path},
    )
    return name


@pytest.fixture(scope="module")
def base_entity(sdk: NeMoPlatform, customizer_workspace: str) -> str:
    """Register the base HF model entity (shared across cases)."""
    return cds.create_hf_model_entity(sdk, customizer_workspace, BASE_ENTITY, BASE_MODEL_HF)


@pytest.mark.parametrize("finetuning_type", ["lora", "all_weights"])
def test_automodel_sft_uplift(
    sdk: NeMoPlatform,
    customizer_workspace: str,
    platform_base_url: str,
    squad_local: tuple,
    squad_fileset: str,
    base_entity: str,
    require_uplift: bool,
    finetuning_type: str,
) -> None:
    ws = customizer_workspace
    _train_path, val_path = squad_local
    output_name = cust.get_unique_name(f"qwen3-{finetuning_type}")

    spec = AutomodelJobInput.model_validate(
        {
            "model": f"{ws}/{base_entity}",
            "dataset": {"training": f"{ws}/{squad_fileset}", "validation": f"{ws}/{squad_fileset}"},
            "training": {
                "training_type": "sft",
                "finetuning_type": finetuning_type,
                "max_seq_length": 1024,
            },
            "schedule": {"epochs": 1},
            "batch": {"global_batch_size": 8, "micro_batch_size": 1},
            "optimizer": {"learning_rate": 1e-4 if finetuning_type == "lora" else 5e-6},
            "parallelism": {"num_nodes": 1, "num_gpus_per_node": 1},
            "output": {"name": output_name},
        }
    )

    job_name, final = cust.submit_and_wait_customization_job(sdk, "automodel", spec, ws)
    assert final.status == "completed", cust.get_job_failure_details(sdk, job_name, ws)

    val_rows = ceval.load_chat_jsonl(str(val_path))

    if finetuning_type == "lora":
        # Base + adapter share one lora_enabled deployment (adapter hot-reloads).
        deployment, config = cust.deploy_vllm_model(sdk, ws, base_entity, lora_enabled=True)
        try:
            base_score = ceval.score_rows(
                val_rows, platform_base_url, ws, deployment, ceval.base_model_field(ws, base_entity)
            )
            tuned_score = ceval.score_rows(
                val_rows, platform_base_url, ws, deployment, ceval.lora_model_field(ws, output_name)
            )
        finally:
            cust.delete_deployment(sdk, ws, deployment, config)
    else:
        # Full weight: base and output entities are distinct — deploy each in turn
        # (serialized to fit a single GPU).
        base_score = _deploy_and_score(sdk, ws, platform_base_url, base_entity, val_rows)
        tuned_score = _deploy_and_score(sdk, ws, platform_base_url, output_name, val_rows)

    result = ceval.UpliftResult(
        metric="f1", base_score=base_score, tuned_score=tuned_score, tuned_label=finetuning_type
    )
    logger.info(
        "automodel %s: base=%.4f tuned=%.4f uplift=%.4f", finetuning_type, base_score, tuned_score, result.uplift
    )
    result.assert_ok(require_uplift=require_uplift)


def _deploy_and_score(
    sdk: NeMoPlatform,
    workspace: str,
    base_url: str,
    entity: str,
    rows: list,
) -> float:
    """Deploy a full-weight entity on vLLM, score it (F1), then tear it down."""
    deployment, config = cust.deploy_vllm_model(sdk, workspace, entity, lora_enabled=False)
    try:
        return ceval.score_rows(rows, base_url, workspace, deployment, ceval.base_model_field(workspace, entity))
    finally:
        cust.delete_deployment(sdk, workspace, deployment, config)
