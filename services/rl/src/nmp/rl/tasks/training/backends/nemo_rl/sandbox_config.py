# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sandbox and Gym-host bootstrap helpers used when compiling GRPO configs."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GymHostEgressRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str
    port: int = Field(ge=1, le=65535)


class SandboxNetworkPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    egress_allow: list[GymHostEgressRule] = Field(default_factory=list)


class SandboxConfig(BaseModel):
    """Mirror of NeMo-RL's ``env.nemo_gym.sandbox`` schema.

    Field names and requiredness must track
    ``nemo_rl/environments/sandbox/host/models.py``: that model is
    ``extra="forbid"`` and declares ``environment_pvc_claim`` and
    ``workspace_pvc_claim`` with no defaults, so omitting either makes the Gym
    host fail validation at provisioning time.
    """

    model_config = ConfigDict(extra="forbid")

    image: str
    # The only egress lever the platform sets; NeMo-RL owns which suffixes it opens. Sourced
    # from platformConfig.rl.sandbox_allow_internet, so it is per-deployment, never per-job.
    # NeMo-RL's public_dns_allow is deliberately not mirrored: with no field to populate, the
    # job schema has no path to widen egress.
    allow_internet: bool = False
    env_mount_path: str = "/job/environment"
    dataset_mount_path: str = "/job/dataset"
    work_mount_path: str = "/job/work"
    max_request_bytes: int = Field(default=268_435_456, gt=0)
    max_response_bytes: int = Field(default=268_435_456, gt=0)
    ttl_s: int = 14_400
    network_policy: SandboxNetworkPolicy = Field(default_factory=SandboxNetworkPolicy)
    resources: dict[str, str] | None = None
    # PVC claim + sub-path triples. The sandbox mounts the same job-storage claim the
    # training container uses, so the environment and dataset it reads are the ones the
    # file_io download step already materialized.
    environment_pvc_claim: str = Field(min_length=1)
    environment_sub_path: str = ""
    dataset_pvc_claim: str | None = None
    dataset_sub_path: str = ""
    workspace_pvc_claim: str = Field(min_length=1)
    workspace_sub_path: str = ""


class NemoGymSandboxedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandboxed: bool = True
    host_provider: str = "opensandbox"
    environment_path: str | None = None
    sandbox: SandboxConfig | None = None
    # Stamped onto every sandbox pod as a label. Upstream defaults this to a shared
    # constant when absent, which makes concurrent jobs indistinguishable.
    job_id: str | None = None


def resolve_ephemeral_work_path(job_id: str) -> str:
    """Prefer node-local ``/scratch`` for lock-heavy Gym/HF work; else ``/tmp``."""
    base = Path("/scratch") if Path("/scratch").is_dir() else Path("/tmp")
    return str(base / "nmp-rl" / job_id / "work")


def resolve_job_storage_pvc_claim() -> str | None:
    """Job-storage PVC claim name injected by the compiler, if any."""
    from nmp.rl.app.constants import NMP_JOB_STORAGE_PVC_ENVVAR

    return os.environ.get(NMP_JOB_STORAGE_PVC_ENVVAR) or None


class SandboxMounts(BaseModel):
    """PVC claim + sub-path triples for the Gym sandbox's three mounts."""

    model_config = ConfigDict(frozen=True)

    environment_pvc_claim: str
    environment_sub_path: str
    dataset_pvc_claim: str
    dataset_sub_path: str
    workspace_pvc_claim: str
    workspace_sub_path: str


def build_sandbox_mounts(
    *,
    pvc_claim: str,
    workspace: str,
    job_id: str,
    storage_root: Path,
    environment_path: str,
    dataset_path: str,
) -> SandboxMounts:
    """Map job-storage directories to PVC-relative sub-paths for the Gym sandbox.

    The training container sees ``environment_path`` / ``dataset_path`` under the
    job-storage mount; the sandbox mounts the same claim directly, so each path has
    to be re-expressed relative to the PVC root.
    """
    from nemo_platform_plugin.jobs.constants import job_storage_subpath

    prefix = job_storage_subpath(workspace, job_id)

    def _sub_path(path: str) -> str:
        leaf = Path(path).relative_to(storage_root)
        return f"{prefix}/{leaf.as_posix()}"

    return SandboxMounts(
        environment_pvc_claim=pvc_claim,
        environment_sub_path=_sub_path(environment_path),
        dataset_pvc_claim=pvc_claim,
        dataset_sub_path=_sub_path(dataset_path),
        workspace_pvc_claim=pvc_claim,
        # Writable scratch for the Gym host, kept beside the job's own data so it is
        # reclaimed by the same job-storage cleanup.
        workspace_sub_path=f"{prefix}/gym-work",
    )


def bootstrap_env_from_job(
    *,
    job_id: str,
    environment_path: str,
    dataset_path: str,
    work_path: str,
    broker_url: str | None = None,
    broker_token: str | None = None,
    gym_global_config_json: str | None = None,
) -> dict[str, str]:
    """Environment variables injected into the Gym job-host bootstrap."""
    env: dict[str, str] = {
        "NMP_JOB_ID": job_id,
        "NMP_ENVIRONMENT_PATH": environment_path,
        "NMP_DATASET_PATH": dataset_path,
        "NMP_WORK_PATH": work_path,
        "NMP_MAX_REQUEST_BYTES": str(268_435_456),
        "NMP_MAX_RESPONSE_BYTES": str(268_435_456),
    }
    if broker_url:
        env["NMP_BROKER_URL"] = broker_url
    if broker_token:
        env["NMP_BROKER_TOKEN"] = broker_token
    if gym_global_config_json:
        env["NMP_GYM_GLOBAL_CONFIG"] = gym_global_config_json
    return env


def assemble_master_egress_allow(
    *,
    vllm_host: str | None = None,
    vllm_port: int | None = None,
    broker_host: str | None = None,
    broker_port: int | None = None,
) -> list[GymHostEgressRule]:
    """Build OpenSandbox egress rules from live vLLM and broker endpoints.

    Explicit kwargs win; otherwise read ``NMP_*_SERVICE_*`` env vars, then
    fall back to localhost defaults suitable for single-node bring-up.
    """
    from nmp.rl.app.constants import (
        NMP_BROKER_HOST_ENVVAR,
        NMP_BROKER_PORT_ENVVAR,
        NMP_VLLM_HOST_ENVVAR,
        NMP_VLLM_PORT_ENVVAR,
    )

    host_vllm = vllm_host or os.environ.get(NMP_VLLM_HOST_ENVVAR) or "127.0.0.1"
    port_vllm = vllm_port if vllm_port is not None else int(os.environ.get(NMP_VLLM_PORT_ENVVAR, "8000"))
    host_broker = broker_host or os.environ.get(NMP_BROKER_HOST_ENVVAR) or "127.0.0.1"
    port_broker = broker_port if broker_port is not None else int(os.environ.get(NMP_BROKER_PORT_ENVVAR, "51234"))
    return [
        GymHostEgressRule(host=host_vllm, port=port_vllm),
        GymHostEgressRule(host=host_broker, port=port_broker),
    ]


def apply_master_egress_to_sandbox_config(sandbox: SandboxConfig) -> SandboxConfig:
    """Refresh ``network_policy.egress_allow`` from the current master endpoints."""
    return sandbox.model_copy(
        update={
            "network_policy": SandboxNetworkPolicy(egress_allow=assemble_master_egress_allow()),
        }
    )
