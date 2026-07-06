# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU e2e: nemo-rl DPO on HelpSteer3, with a deterministic uplift proxy.

Flow: upload HelpSteer3 preference data (``training.jsonl`` + ``validation.jsonl``
to one fileset) → register base entity → submit an ``rl`` DPO job → deploy base and
DPO output entities on vLLM → score both.

DPO has no single gold label, so uplift is a **deterministic proxy** (no LLM judge):
token-overlap F1 of the model's generation against the *preferred* response
(``response1`` if ``overall_preference < 0`` else ``response2``, ties dropped). A
DPO-aligned model should overlap the preferred response at least as much as the
base. rl runs each step as a Kubernetes pod, so the test skips unless the platform
reports a ``kubernetes_job``/``volcano_job`` execution backend.
"""

from __future__ import annotations

import logging

import pytest
from nemo_platform import NeMoPlatform
from nemo_rl_plugin.schema import RlJobInput
from nmp.testing.e2e import customizer as cust
from nmp.testing.e2e import customizer_datasets as cds
from nmp.testing.e2e import customizer_eval as ceval

logger = logging.getLogger(__name__)

BASE_MODEL_HF = "Qwen/Qwen3-0.6B"
BASE_ENTITY = "qwen3-0-6b-rl"


def _require_kubernetes_backend(sdk: NeMoPlatform) -> None:
    """Skip unless the platform dispatches jobs to a Kubernetes execution backend."""
    try:
        profiles = sdk.jobs.list_execution_profiles()
    except Exception as exc:  # noqa: BLE001 - any failure means we can't confirm the backend
        pytest.skip(f"could not list execution profiles to verify rl backend: {exc}")
    text = str(profiles)
    if "kubernetes_job" not in text and "volcano_job" not in text:
        pytest.skip(
            "rl (DPO) requires a kubernetes_job/volcano_job execution backend; platform is not configured for it"
        )


def _deploy_and_score(sdk: NeMoPlatform, workspace: str, base_url: str, entity: str, rows: list) -> float:
    """Deploy a full-weight entity on vLLM, score overlap-F1, then tear it down."""
    deployment, config = cust.deploy_vllm_model(sdk, workspace, entity, lora_enabled=False)
    try:
        return ceval.score_rows(
            rows, base_url, workspace, deployment, ceval.base_model_field(workspace, entity), metric="f1"
        )
    finally:
        cust.delete_deployment(sdk, workspace, deployment, config)


def test_rl_dpo_uplift(
    sdk: NeMoPlatform,
    customizer_workspace: str,
    platform_base_url: str,
    helpsteer_local: tuple,
    require_uplift: bool,
) -> None:
    _require_kubernetes_backend(sdk)

    ws = customizer_workspace
    training_path, validation_path = helpsteer_local

    # rl requires both files in ONE fileset at the expected names.
    dataset_fs = cust.get_unique_name("helpsteer3-dpo")
    cds.create_dataset_fileset(
        sdk,
        ws,
        dataset_fs,
        {"training.jsonl": training_path, "validation.jsonl": validation_path},
    )

    base_entity = cds.create_hf_model_entity(sdk, ws, BASE_ENTITY, BASE_MODEL_HF)
    output_name = cust.get_unique_name("qwen3-dpo")

    spec = RlJobInput.model_validate(
        {
            "model": f"{ws}/{base_entity}",
            "dataset": f"{ws}/{dataset_fs}",
            "training": {
                "type": "dpo",
                "epochs": 1,
                "batch_size": 32,
                "micro_batch_size": 1,
                "learning_rate": 5e-6,
                "max_seq_length": 1024,
                "ref_policy_kl_penalty": 0.05,
                "parallelism": {"num_nodes": 1, "num_gpus_per_node": 1},
            },
            "output": {"name": output_name},
        }
    )

    job_name, final = cust.submit_and_wait_customization_job(sdk, "rl", spec, ws)
    assert final.status == "completed", cust.get_job_failure_details(sdk, job_name, ws)

    eval_rows = cds.prepare_dpo_eval_rows(validation_path)
    assert eval_rows, "no non-tie preference rows available for DPO eval"

    base_score = _deploy_and_score(sdk, ws, platform_base_url, base_entity, eval_rows)
    tuned_score = _deploy_and_score(sdk, ws, platform_base_url, output_name, eval_rows)

    result = ceval.UpliftResult(metric="f1", base_score=base_score, tuned_score=tuned_score, tuned_label="dpo")
    logger.info("rl dpo: base=%.4f tuned=%.4f uplift=%.4f", base_score, tuned_score, result.uplift)
    result.assert_ok(require_uplift=require_uplift)
