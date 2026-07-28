# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remote Harbor evaluator that never receives Docker authority."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

import httpx
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    Dataset,
    EvaluationResult,
    TrialResult,
    local_path_from_uri,
)
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    create_directory_archive,
    materialize_result_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import HarborBridgeRequest
from pydantic import AnyHttpUrl, ConfigDict, Field

BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"


class RemoteHarborEvaluatorConfig(EvaluatorConfig):
    """Bounded client configuration for the trusted Harbor bridge."""

    model_config = ConfigDict(extra="forbid")

    bridge_url: AnyHttpUrl
    bridge_token_env: str = Field(
        default="NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
        pattern=r"^[A-Z_][A-Z0-9_]*$",
    )
    request_timeout_sec: float = Field(default=3600.0, ge=1.0, le=86_400.0)
    max_archive_bytes: int = Field(default=DEFAULT_MAX_ARCHIVE_BYTES, ge=1, le=2 * 1024 * 1024 * 1024)
    result_dir: Path = Field(default=Path("eval-and-optimize") / "remote-results")
    job_name: str | None = Field(default=None, min_length=1, max_length=80)
    n_attempts: int = Field(default=1, ge=1, le=8)
    n_concurrent_trials: int = Field(default=4, ge=1, le=16)
    quiet: bool = Field(
        default=True,
        description="Accepted for compatibility; the trusted bridge always runs Harbor quietly.",
    )
    agent_model_name: str | None = Field(default=None, min_length=1, max_length=256)
    agent_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    verifier_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    agent_setup_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    environment_build_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)


def _request_id(agent: Path, dataset: Dataset, configured: str | None) -> str:
    raw = configured or f"{agent.name}-{dataset.id}"
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("._-") or "evaluation"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:60]}-{digest}"


class RemoteHarborEvaluator(Evaluator):
    """Submit candidate and dataset bundles to the narrow Harbor bridge."""

    evaluator_type: EvaluatorType = "harbor"

    def __init__(
        self,
        options: RemoteHarborEvaluatorConfig,
        experiment_dir: Path | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(options, experiment_dir=experiment_dir)
        self.options = options
        self._client = client

    async def _run(
        self,
        agent: Path,
        dataset: Dataset,
        options: EvaluatorConfig,
    ) -> list[TrialResult]:
        if not isinstance(options, RemoteHarborEvaluatorConfig):
            raise TypeError("Remote Harbor evaluator requires RemoteHarborEvaluatorConfig")
        if not isinstance(dataset, HarborDataset):
            raise ValueError("Dataset must be a Harbor dataset")
        if dataset.source is None:
            raise ValueError("Harbor dataset source is required")

        agent_path = agent.expanduser().resolve()
        dataset_path = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()
        if not agent_path.is_dir():
            raise FileNotFoundError(f"Harbor agent path not found: {agent_path}")
        if not dataset_path.is_dir():
            raise FileNotFoundError(f"Harbor dataset path not found: {dataset_path}")
        await dataset.validate()

        token = os.environ.get(options.bridge_token_env)
        if not token:
            raise ValueError(f"Harbor bridge token environment variable is not set: {options.bridge_token_env}")

        request_id = _request_id(agent_path, dataset, options.job_name)
        experiment_dir = (self.experiment_dir or Path.cwd()).resolve()
        result_dir = experiment_dir / options.result_dir / request_id
        result_path = result_dir / "result.json"
        if result_path.is_file() and not options.force_rerun:
            return list(materialize_result_archive_from_directory(result_dir).trials)

        staging = experiment_dir / "tmp" / "harbor-bridge" / f"{request_id}-{uuid4().hex[:8]}"
        staging.mkdir(parents=True, exist_ok=False)
        candidate_archive = staging / "candidate.tar.gz"
        dataset_archive = staging / "dataset.tar.gz"
        response_archive = staging / "response.tar.gz"
        try:
            create_directory_archive(agent_path, candidate_archive, max_bytes=options.max_archive_bytes)
            create_directory_archive(dataset_path, dataset_archive, max_bytes=options.max_archive_bytes)
            request = HarborBridgeRequest(
                request_id=request_id,
                task_ids=[task.id for task in dataset.tasks],
                n_attempts=options.n_attempts,
                n_concurrent_trials=options.n_concurrent_trials,
                agent_model_name=options.agent_model_name,
                agent_timeout_multiplier=options.agent_timeout_multiplier,
                verifier_timeout_multiplier=options.verifier_timeout_multiplier,
                agent_setup_timeout_multiplier=options.agent_setup_timeout_multiplier,
                environment_build_timeout_multiplier=options.environment_build_timeout_multiplier,
            )
            await self._submit(
                options,
                token=token,
                request=request,
                candidate_archive=candidate_archive,
                dataset_archive=dataset_archive,
                response_archive=response_archive,
            )
            if result_dir.exists():
                shutil.rmtree(result_dir)
            result_dir.mkdir(parents=True)
            result = materialize_result_archive(response_archive, result_dir)
            return list(result.trials)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    async def _submit(
        self,
        options: RemoteHarborEvaluatorConfig,
        *,
        token: str,
        request: HarborBridgeRequest,
        candidate_archive: Path,
        dataset_archive: Path,
        response_archive: Path,
    ) -> None:
        url = f"{str(options.bridge_url).rstrip('/')}/v1/evaluations"
        with candidate_archive.open("rb") as candidate, dataset_archive.open("rb") as dataset:
            files = {
                "candidate": ("candidate.tar.gz", candidate, "application/gzip"),
                "dataset": ("dataset.tar.gz", dataset, "application/gzip"),
            }
            data = {"request": request.model_dump_json()}
            headers = {"Authorization": f"Bearer {token}"}
            if self._client is not None:
                response = await self._client.post(url, data=data, files=files, headers=headers)
            else:
                timeout = httpx.Timeout(options.request_timeout_sec)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, data=data, files=files, headers=headers)
        if response.status_code != 200:
            detail = response.text[:4000]
            raise RuntimeError(f"Harbor bridge returned HTTP {response.status_code}: {detail}")
        if response.headers.get("content-type", "").split(";", 1)[0] != "application/gzip":
            raise RuntimeError(
                f"Harbor bridge returned unexpected content type: {response.headers.get('content-type')}"
            )
        if len(response.content) > options.max_archive_bytes:
            raise RuntimeError(f"Harbor bridge response exceeds {options.max_archive_bytes} bytes")
        response_archive.write_bytes(response.content)


def materialize_result_archive_from_directory(result_dir: Path) -> EvaluationResult:
    """Load a previously materialized bridge result without changing its URIs."""
    return EvaluationResult.model_validate_json((result_dir / "result.json").read_text(encoding="utf-8"))
