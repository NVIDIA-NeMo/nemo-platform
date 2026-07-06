# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU e2e: unsloth LoRA SFT on SQuAD, with uplift eval.

Unsloth's primary path is single-GPU LoRA. Flow: prepare SQuAD CHAT data →
register base entity → submit an ``unsloth`` LoRA job (``save_method='lora'``) →
deploy the base on vLLM with ``lora_enabled`` (the completed job auto-registers the
adapter, which hot-reloads) → deterministic base-vs-adapter uplift (F1).

Unsloth resolves ``dataset.path`` / ``dataset.validation_path`` as *fileset*
references and downloads each whole fileset, so train and val go to separate
filesets. ``load_in_4bit=False`` keeps the training base at the same precision as
the fp16 vLLM deployment the adapter is served against.
"""

from __future__ import annotations

import logging

from nemo_platform import NeMoPlatform
from nemo_unsloth_plugin.schema import UnslothJobInput
from nmp.testing.e2e import customizer as cust
from nmp.testing.e2e import customizer_datasets as cds
from nmp.testing.e2e import customizer_eval as ceval

logger = logging.getLogger(__name__)

BASE_MODEL_HF = "unsloth/Qwen2.5-0.5B-Instruct"
BASE_ENTITY = "qwen25-05b-unsloth"


def test_unsloth_lora_uplift(
    sdk: NeMoPlatform,
    customizer_workspace: str,
    platform_base_url: str,
    squad_local: tuple,
    require_uplift: bool,
) -> None:
    ws = customizer_workspace
    train_path, val_path = squad_local

    # Separate train / val filesets (unsloth downloads each whole fileset).
    train_fs = cust.get_unique_name("squad-train")
    val_fs = cust.get_unique_name("squad-val")
    cds.create_dataset_fileset(sdk, ws, train_fs, {"train.jsonl": train_path})
    cds.create_dataset_fileset(sdk, ws, val_fs, {"validation.jsonl": val_path})

    base_entity = cds.create_hf_model_entity(sdk, ws, BASE_ENTITY, BASE_MODEL_HF)
    output_name = cust.get_unique_name("qwen25-unsloth-lora")

    spec = UnslothJobInput.model_validate(
        {
            "model": {"name": f"{ws}/{base_entity}", "max_seq_length": 1024, "load_in_4bit": False},
            "dataset": {
                "path": f"{ws}/{train_fs}",
                "validation_path": f"{ws}/{val_fs}",
                "apply_chat_template": True,
            },
            "training": {"finetuning_type": "lora"},
            "schedule": {"epochs": 1},
            "optimizer": {"learning_rate": 1e-4},
            "output": {"name": output_name, "save_method": "lora"},
        }
    )

    job_name, final = cust.submit_and_wait_customization_job(sdk, "unsloth", spec, ws)
    assert final.status == "completed", cust.get_job_failure_details(sdk, job_name, ws)

    val_rows = ceval.load_chat_jsonl(str(val_path))
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

    result = ceval.UpliftResult(metric="f1", base_score=base_score, tuned_score=tuned_score, tuned_label="lora")
    logger.info("unsloth lora: base=%.4f tuned=%.4f uplift=%.4f", base_score, tuned_score, result.uplift)
    result.assert_ok(require_uplift=require_uplift)
