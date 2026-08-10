# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GRPO sandbox / master egress helpers."""

from __future__ import annotations

import pytest
from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
    GymHostEgressRule,
    SandboxConfig,
    SandboxNetworkPolicy,
    apply_master_egress_to_sandbox_config,
    assemble_master_egress_allow,
    bootstrap_env_from_job,
    resolve_ephemeral_work_path,
)


def test_assemble_master_egress_allow_defaults() -> None:
    rules = assemble_master_egress_allow()
    assert rules == [
        GymHostEgressRule(host="127.0.0.1", port=8000),
        GymHostEgressRule(host="127.0.0.1", port=51234),
    ]


def test_assemble_master_egress_allow_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_VLLM_SERVICE_HOST", "vllm.svc")
    monkeypatch.setenv("NMP_VLLM_SERVICE_PORT", "9000")
    monkeypatch.setenv("NMP_BROKER_SERVICE_HOST", "broker.svc")
    monkeypatch.setenv("NMP_BROKER_SERVICE_PORT", "51235")
    rules = assemble_master_egress_allow()
    assert [(r.host, r.port) for r in rules] == [
        ("vllm.svc", 9000),
        ("broker.svc", 51235),
    ]


def test_assemble_master_egress_allow_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_VLLM_SERVICE_HOST", "env-host")
    rules = assemble_master_egress_allow(vllm_host="explicit", vllm_port=1, broker_host="b", broker_port=2)
    assert [(r.host, r.port) for r in rules] == [("explicit", 1), ("b", 2)]


def test_apply_master_egress_to_sandbox_config() -> None:
    sandbox = SandboxConfig(
        image="nvcr.io/example/rl:latest",
        network_policy=SandboxNetworkPolicy(egress_allow=[GymHostEgressRule(host="placeholder", port=1)]),
    )
    updated = apply_master_egress_to_sandbox_config(sandbox)
    assert updated.network_policy.egress_allow == assemble_master_egress_allow()
    # original unchanged (pydantic copy)
    assert sandbox.network_policy.egress_allow[0].host == "placeholder"


def test_bootstrap_env_from_job_keys() -> None:
    env = bootstrap_env_from_job(
        job_id="job-1",
        environment_path="/job/environment",
        dataset_path="/job/dataset",
        work_path="/job/work",
        broker_url="http://broker:51234",
        broker_token="tok",
        gym_global_config_json="{}",
    )
    assert env["NMP_JOB_ID"] == "job-1"
    assert env["NMP_ENVIRONMENT_PATH"] == "/job/environment"
    assert env["NMP_DATASET_PATH"] == "/job/dataset"
    assert env["NMP_WORK_PATH"] == "/job/work"
    assert env["NMP_BROKER_URL"] == "http://broker:51234"
    assert env["NMP_BROKER_TOKEN"] == "tok"
    assert env["NMP_GYM_GLOBAL_CONFIG"] == "{}"


def test_resolve_ephemeral_work_path_uses_tmp_when_no_scratch() -> None:
    path = resolve_ephemeral_work_path("abc123")
    assert path.endswith("/nmp-rl/abc123/work")
    assert path.startswith("/scratch/") or path.startswith("/tmp/")
