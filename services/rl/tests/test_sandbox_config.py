# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GRPO sandbox / master egress helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
    GymHostEgressRule,
    SandboxConfig,
    SandboxNetworkPolicy,
    apply_master_egress_to_sandbox_config,
    assemble_master_egress_allow,
    bootstrap_env_from_job,
    build_sandbox_mounts,
    resolve_ephemeral_work_path,
)
from pydantic import ValidationError


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


def _sandbox_config() -> SandboxConfig:
    return SandboxConfig(
        image="nvcr.io/example/rl:latest",
        network_policy=SandboxNetworkPolicy(egress_allow=[GymHostEgressRule(host="placeholder", port=1)]),
        environment_pvc_claim="nmp-job-storage",
        workspace_pvc_claim="nmp-job-storage",
    )


def test_sandbox_config_requires_pvc_claims() -> None:
    """Upstream declares these with no defaults; omitting them fails the Gym host
    at provisioning time rather than at compile time."""
    with pytest.raises(ValidationError) as exc:
        SandboxConfig.model_validate({"image": "nvcr.io/example/rl:latest"})
    missing = {e["loc"][0] for e in exc.value.errors()}
    assert {"environment_pvc_claim", "workspace_pvc_claim"} <= missing


def test_build_sandbox_mounts_maps_paths_to_pvc_subpaths() -> None:
    mounts = build_sandbox_mounts(
        pvc_claim="nmp-job-storage",
        workspace="default",
        job_id="job-9",
        storage_root=Path("/var/run/scratch/job"),
        environment_path="/var/run/scratch/job/environment",
        dataset_path="/var/run/scratch/job/dataset",
    )
    assert mounts.environment_sub_path == "jobs/default/job-9/environment"
    assert mounts.dataset_sub_path == "jobs/default/job-9/dataset"
    assert mounts.workspace_sub_path == "jobs/default/job-9/gym-work"
    assert mounts.environment_pvc_claim == "nmp-job-storage"


def test_apply_master_egress_to_sandbox_config() -> None:
    sandbox = _sandbox_config()
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


def test_egress_is_operator_scoped_not_per_job() -> None:
    """The job schema must have no path to widen sandbox egress.

    Both levers -- allow_internet and public_dns_allow -- are resolved by the compiler from
    RlConfig, so they are per-deployment. Asserting on the submission schema is what actually
    pins the invariant: the compiler-side models legitimately carry both fields.
    """
    from nmp.rl.schemas.job import GRPOTraining

    for field in ("allow_internet", "public_dns_allow", "egress_allow", "network_policy"):
        assert field not in GRPOTraining.model_fields

    with pytest.raises(ValidationError):
        GRPOTraining(public_dns_allow=("evil.example",))


def test_sandbox_config_carries_both_operator_egress_levers() -> None:
    from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
        SandboxConfig,
        SandboxNetworkPolicy,
    )

    common = {"environment_pvc_claim": "c", "workspace_pvc_claim": "c"}
    assert SandboxConfig(image="i", **common).allow_internet is False
    assert SandboxConfig(image="i", allow_internet=True, **common).allow_internet is True

    assert SandboxNetworkPolicy().public_dns_allow == ()
    policy = SandboxNetworkPolicy(public_dns_allow=("hub.primeintellect.ai",))
    assert policy.public_dns_allow == ("hub.primeintellect.ai",)


def test_master_egress_refresh_preserves_public_dns_allow() -> None:
    """Refreshing vLLM/broker endpoints must not drop operator DNS configuration."""
    from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
        SandboxConfig,
        SandboxNetworkPolicy,
        apply_master_egress_to_sandbox_config,
    )

    sandbox = SandboxConfig(
        image="i",
        environment_pvc_claim="c",
        workspace_pvc_claim="c",
        network_policy=SandboxNetworkPolicy(public_dns_allow=("hub.primeintellect.ai",)),
    )
    refreshed = apply_master_egress_to_sandbox_config(sandbox)
    assert refreshed.network_policy.public_dns_allow == ("hub.primeintellect.ai",)
    assert refreshed.network_policy.egress_allow  # recomputed from master endpoints
