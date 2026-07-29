# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remote Harbor evaluator that never receives Docker authority."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import shutil
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import uuid4

import httpx
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    Dataset,
    DependencyCommandResult,
    DependencyRuntime,
    DependencyRuntimeError,
    EvaluationResult,
    ResourceRef,
    TrialResult,
    local_path_from_uri,
)
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    create_directory_archive,
    materialize_result_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    HarborBridgeRequest,
    HarborDependencyExecRequest,
    HarborDependencyExecResponse,
    HarborDependencyRequest,
    HarborDependencySessionResponse,
)
from pydantic import AnyHttpUrl, ConfigDict, Field, PrivateAttr, model_validator

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


class RemoteHarborDependencyRuntime(DependencyRuntime):
    """Harbor task environment owned by the authenticated bridge."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    task_path: ResourceRef
    bridge_url: AnyHttpUrl
    bridge_token_env: str = Field(
        default="NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
        pattern=r"^[A-Z_][A-Z0-9_]*$",
    )
    request_timeout_sec: float = Field(default=3600.0, ge=1.0, le=86_400.0)
    max_archive_bytes: int = Field(default=DEFAULT_MAX_ARCHIVE_BYTES, ge=1, le=2 * 1024 * 1024 * 1024)
    force_build: bool = True
    run_healthcheck: bool = True
    build_timeout_sec: int | None = Field(default=None, ge=1, le=3600)

    _session_id: str | None = PrivateAttr(default=None)
    _client: httpx.AsyncClient | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def reject_local_commands(self) -> RemoteHarborDependencyRuntime:
        """Keep task commands behind the bridge instead of spawning locally."""
        if self.start is not None or self.stop is not None or self.readiness is not None:
            raise ValueError("Remote Harbor dependencies do not accept local start, readiness, or stop commands")
        return self

    def context(self) -> RemoteHarborDependencyContext:
        """Return the bridge-backed dependency context."""
        session_runtime = self.model_copy(deep=False)
        session_runtime._session_id = None
        session_runtime._client = self._client
        return RemoteHarborDependencyContext(session_runtime)

    async def execute(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout: float = 30.0,
    ) -> DependencyCommandResult:
        """Execute an analyzer shell command in the active Harbor task environment."""
        if self._session_id is None:
            raise DependencyRuntimeError("Remote Harbor dependency session is not running")
        request = HarborDependencyExecRequest(
            command=command,
            stdin=stdin,
            timeout_sec=max(1, math.ceil(timeout)),
        )
        response = await self._send(
            "POST",
            f"/v1/dependencies/{self._session_id}/exec",
            json=request.model_dump(),
            timeout_sec=max(self.request_timeout_sec, request.timeout_sec + 30),
        )
        self._require_status(response, 200, context="command")
        try:
            result = HarborDependencyExecResponse.model_validate_json(response.content)
        except ValueError as exc:
            raise DependencyRuntimeError("Harbor bridge returned an invalid dependency command response") from exc
        return DependencyCommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    async def _start(self) -> None:
        if self._session_id is not None:
            raise DependencyRuntimeError("Remote Harbor dependency session is already running")

        task_path = local_path_from_uri(self.task_path.uri, context="Harbor task reference").resolve()
        if not task_path.is_dir():
            raise DependencyRuntimeError(f"Harbor task path not found: {task_path}")

        request = HarborDependencyRequest(
            request_id=_dependency_request_id(self.task_id, task_path),
            task_id=self.task_id,
            force_build=self.force_build,
            run_healthcheck=self.run_healthcheck,
            build_timeout_sec=self.build_timeout_sec,
        )
        staging = Path.cwd().resolve() / "tmp" / "harbor-bridge" / f"{request.request_id}-{uuid4().hex[:8]}"
        staging.mkdir(parents=True, exist_ok=False)
        task_archive = staging / "task.tar.gz"
        try:
            create_directory_archive(task_path, task_archive, max_bytes=self.max_archive_bytes)
            with task_archive.open("rb") as task:
                response = await self._send(
                    "POST",
                    "/v1/dependencies",
                    data={"request": request.model_dump_json()},
                    files={"task": ("task.tar.gz", task, "application/gzip")},
                    timeout_sec=self.request_timeout_sec,
                )
            self._require_status(response, 201, context="startup")
            try:
                session = HarborDependencySessionResponse.model_validate_json(response.content)
            except ValueError as exc:
                raise DependencyRuntimeError("Harbor bridge returned an invalid dependency startup response") from exc
            self._session_id = session.session_id
            self.metadata.update(
                {
                    "execution_boundary": "remote-harbor-bridge",
                    "harbor_dependency_session_id": session.session_id,
                }
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    async def _stop(self) -> None:
        if self._session_id is None:
            return
        session_id = self._session_id
        response = await self._send(
            "DELETE",
            f"/v1/dependencies/{session_id}",
            timeout_sec=self.request_timeout_sec,
        )
        self._require_status(response, 204, context="shutdown")
        self._session_id = None
        self.metadata.pop("harbor_dependency_session_id", None)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        timeout_sec: float,
        **kwargs: Any,
    ) -> httpx.Response:
        token = os.environ.get(self.bridge_token_env)
        if not token:
            raise DependencyRuntimeError(
                f"Harbor bridge token environment variable is not set: {self.bridge_token_env}"
            )
        url = f"{str(self.bridge_url).rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            if self._client is not None:
                return await self._client.request(method, url, headers=headers, **kwargs)
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
                return await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise DependencyRuntimeError(f"Harbor bridge dependency request failed: {exc}") from exc

    @staticmethod
    def _require_status(response: httpx.Response, expected: int, *, context: str) -> None:
        if response.status_code == expected:
            return
        detail = response.text[:4000]
        raise DependencyRuntimeError(
            f"Harbor bridge dependency {context} returned HTTP {response.status_code}: {detail}"
        )


class RemoteHarborDependencyContext:
    """Start and stop one bridge-owned Harbor dependency session."""

    def __init__(self, runtime: RemoteHarborDependencyRuntime) -> None:
        self._runtime = runtime

    async def __aenter__(self) -> DependencyRuntime:
        try:
            await self._runtime._start()
        except asyncio.CancelledError:
            try:
                await self._runtime._stop()
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                await self._runtime._stop()
            except Exception:
                pass
            if isinstance(exc, DependencyRuntimeError):
                raise
            raise DependencyRuntimeError(f"Remote Harbor dependency startup failed: {exc}") from exc
        return self._runtime

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            await self._runtime._stop()
        except Exception:
            if exc_type is None:
                raise
        return False


def _dependency_request_id(task_id: str, task_path: Path) -> str:
    raw = f"{task_id}:{task_path}"
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", task_id).strip("._-") or "task"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"dependency-{normalized[:48]}-{digest}"


def _request_id(agent: Path, dataset: Dataset, configured: str | None) -> str:
    raw = configured or f"{agent.name}-{dataset.id}"
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("._-") or "evaluation"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:60]}-{digest}"


class RemoteHarborEvaluator(Evaluator):
    """Submit candidate and dataset bundles to the narrow Harbor bridge."""

    evaluator_type: EvaluatorType = "harbor"
    options: RemoteHarborEvaluatorConfig

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

    def prepare_dataset(
        self,
        dataset: Dataset,
        options: RemoteHarborEvaluatorConfig | None = None,
    ) -> Dataset:
        """Replace Docker-backed Harbor task runtimes with bridge-backed runtimes."""
        if not isinstance(dataset, HarborDataset):
            raise ValueError("Dataset must be a Harbor dataset")
        runtime_options = options or self.options
        for task in dataset.tasks:
            dependencies = task.dependencies
            if dependencies is None:
                continue
            if isinstance(dependencies, RemoteHarborDependencyRuntime):
                continue
            if not isinstance(dependencies, HarborDependencyRuntime):
                raise DependencyRuntimeError(
                    f"Remote Harbor evaluator will not run unsupported task dependencies locally: {task.id}"
                )
            if dependencies.environment_type != "docker":
                raise DependencyRuntimeError(f"Remote Harbor dependencies require environment_type='docker': {task.id}")
            if not dependencies.delete:
                raise DependencyRuntimeError(
                    f"Remote Harbor dependencies require delete=true so bridge sessions cannot leak: {task.id}"
                )
            if dependencies.start is not None or dependencies.readiness is not None or dependencies.stop is not None:
                raise DependencyRuntimeError(
                    f"Remote Harbor dependencies do not support custom lifecycle commands: {task.id}"
                )
            task.dependencies = RemoteHarborDependencyRuntime(
                task_id=task.id,
                task_path=dependencies.task_path,
                bridge_url=runtime_options.bridge_url,
                bridge_token_env=runtime_options.bridge_token_env,
                request_timeout_sec=runtime_options.request_timeout_sec,
                max_archive_bytes=runtime_options.max_archive_bytes,
                force_build=dependencies.force_build,
                run_healthcheck=dependencies.run_healthcheck,
                build_timeout_sec=dependencies.build_timeout_sec,
                metadata={
                    **dependencies.metadata,
                    "execution_boundary": "remote-harbor-bridge",
                },
            )
        return dataset

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
        self.prepare_dataset(dataset, options)

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
