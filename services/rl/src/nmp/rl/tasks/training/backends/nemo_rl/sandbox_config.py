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
    model_config = ConfigDict(extra="forbid")

    image: str
    env_mount_path: str = "/job/environment"
    dataset_mount_path: str = "/job/dataset"
    work_mount_path: str = "/job/work"
    max_request_bytes: int = Field(default=268_435_456, gt=0)
    max_response_bytes: int = Field(default=268_435_456, gt=0)
    ttl_s: int = 14_400
    network_policy: SandboxNetworkPolicy = Field(default_factory=SandboxNetworkPolicy)
    resources: dict[str, str] | None = None


class NemoGymSandboxedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandboxed: bool = True
    host_provider: str = "opensandbox"
    environment_path: str | None = None
    sandbox: SandboxConfig | None = None


def resolve_ephemeral_work_path(job_id: str) -> str:
    """Prefer node-local ``/scratch`` for lock-heavy Gym/HF work; else ``/tmp``."""
    base = Path("/scratch") if Path("/scratch").is_dir() else Path("/tmp")
    return str(base / "nmp-rl" / job_id / "work")


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
    port_broker = (
        broker_port if broker_port is not None else int(os.environ.get(NMP_BROKER_PORT_ENVVAR, "51234"))
    )
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
