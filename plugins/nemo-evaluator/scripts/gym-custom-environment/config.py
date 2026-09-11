# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration shared by the custom Gym environment implementation modules.

``run.py`` creates one ``Settings`` object from documented environment
variables and passes it into ``workflow.py``. The dataclasses here centralize
cluster names, temporary Platform resource names, and evidence paths so those
values are derived consistently throughout a run.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ENVIRONMENT_PREFIX = "NMP_GYM_CUSTOM_"


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Filesystem locations generated during one workflow run."""

    root: Path
    evidence: Path
    converter_environment: Path
    converter_dataset: Path
    environment: Path
    dataset: Path

    @classmethod
    def create(cls, root: Path) -> RunPaths:
        """Derive every generated path from one run directory."""
        return cls(
            root=root,
            evidence=root / "evidence",
            converter_environment=root / "converter-environment",
            converter_dataset=root / "converter-dataset",
            environment=root / "environment",
            dataset=root / "dataset.jsonl",
        )


@dataclass(frozen=True, slots=True)
class Settings:
    """Workflow inputs, cluster prerequisites, and run-scoped resource names."""

    repo_root: Path
    asset_root: Path
    paths: RunPaths
    environment_source: Path | None
    dataset_source: Path | None
    requested_resources_server: str | None
    namespace: str
    release: str
    workspace: str
    job_pvc: str
    registry_secret: str
    opensandbox_namespace: str
    opensandbox_service: str
    opensandbox_api_secret: str
    platform_api_service: str
    local_port: int
    model_entity_id: str
    fileset: str
    inference_secret: str
    inference_provider: str

    @classmethod
    def from_environment(
        cls,
        *,
        run_dir: Path | None = None,
        environment_dir: Path | None = None,
        dataset: Path | None = None,
        resources_server: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> Settings:
        """Load inputs and optional overrides, rejecting incomplete custom input."""
        if (environment_dir is None) != (dataset is None):
            raise ValueError("--environment-dir and --dataset must be supplied together")
        if resources_server is not None and not resources_server.strip():
            raise ValueError("--resources-server cannot be empty")

        env = dict(os.environ if environment is None else environment)
        asset_root = Path(__file__).resolve().parent
        repo_root = asset_root.parents[3]
        generated_run_id = f"{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
        run_id = env.get(f"{ENVIRONMENT_PREFIX}RUN_ID", generated_run_id)
        default_run_dir = Path(f"/tmp/nmp-gym-custom-environment-{run_id}")
        workspace = env.get(f"{ENVIRONMENT_PREFIX}WORKSPACE", "default")

        return cls(
            repo_root=repo_root,
            asset_root=asset_root,
            paths=RunPaths.create((run_dir or default_run_dir).resolve()),
            environment_source=environment_dir.resolve() if environment_dir is not None else None,
            dataset_source=dataset.resolve() if dataset is not None else None,
            requested_resources_server=resources_server,
            namespace=env.get(f"{ENVIRONMENT_PREFIX}NAMESPACE", "nmp-temp1"),
            release=env.get(f"{ENVIRONMENT_PREFIX}RELEASE", "nemo-platform"),
            workspace=workspace,
            job_pvc=env.get(f"{ENVIRONMENT_PREFIX}JOB_PVC", "nemo-platform-core-storage"),
            registry_secret=env.get(f"{ENVIRONMENT_PREFIX}REGISTRY_SECRET", "nvcrimagepullsecret"),
            opensandbox_namespace=env.get(
                f"{ENVIRONMENT_PREFIX}OPENSANDBOX_NAMESPACE",
                "opensandbox-system",
            ),
            opensandbox_service=env.get(
                f"{ENVIRONMENT_PREFIX}OPENSANDBOX_SERVICE",
                "opensandbox-server-crun",
            ),
            opensandbox_api_secret=env.get(
                f"{ENVIRONMENT_PREFIX}OPENSANDBOX_API_SECRET",
                "opensandbox-server-crun-api-key",
            ),
            platform_api_service=env.get(
                f"{ENVIRONMENT_PREFIX}PLATFORM_API_SERVICE",
                "nemo-platform-api",
            ),
            local_port=int(env.get(f"{ENVIRONMENT_PREFIX}LOCAL_PORT", "18080")),
            model_entity_id=env.get(
                f"{ENVIRONMENT_PREFIX}MODEL_ENTITY_ID",
                f"{workspace}/nvidia-meta-llama-3-3-70b-instruct",
            ),
            fileset=env.get(
                f"{ENVIRONMENT_PREFIX}FILESET",
                f"gym-custom-environment-{run_id}",
            ),
            inference_secret=env.get(
                f"{ENVIRONMENT_PREFIX}SECRET",
                f"gym-custom-inference-key-{run_id}",
            ),
            inference_provider=env.get(
                f"{ENVIRONMENT_PREFIX}PROVIDER",
                f"gym-custom-inference-hub-{run_id}",
            ),
        )

    @property
    def base_url(self) -> str:
        """Return the workstation URL for the temporary API port-forward."""
        return f"http://127.0.0.1:{self.local_port}"

    @property
    def internal_api(self) -> str:
        """Return the Platform API URL reachable from sandbox pods."""
        return f"http://{self.platform_api_service}.{self.namespace}.svc.cluster.local:8080"

    @property
    def uses_default_example(self) -> bool:
        """Return whether the workflow should prepare its bundled example inputs."""
        return self.environment_source is None
