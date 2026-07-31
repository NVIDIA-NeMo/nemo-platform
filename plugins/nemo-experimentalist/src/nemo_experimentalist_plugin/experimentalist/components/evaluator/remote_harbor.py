# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenShell-side Harbor evaluator and dependency client."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Literal
from urllib.parse import unquote, urlparse
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
    HarborEvaluatorConfig,
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
    create_directory_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    ArchiveReference,
    DependencyExecRequest,
    DependencyExecResponse,
    DependencySession,
    DependencyStartRequest,
    EnvelopeTask,
    EvaluationAccepted,
    EvaluationEnvelope,
    EvaluationState,
    EvaluationStatus,
    EvaluationSubmission,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    ResolvedEnvelopeTask,
    TaskEnvelopePolicy,
    create_overlay_directory,
    resolve_envelope_task,
    transport_tree_digest,
)
from pydantic import AnyHttpUrl, ConfigDict, Field, PrivateAttr, model_validator

OPEN_SHELL_RUNTIME_ENV = "NEMO_EXPERIMENTALIST_OPEN_SHELL_RUNTIME"
BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"
BRIDGE_TOKEN_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
logger = logging.getLogger(__name__)


def _result_resource_refs(result: EvaluationResult) -> Iterator[ResourceRef]:
    for trial in result.trials:
        if trial.trace is not None:
            yield trial.trace
        yield from trial.resources.values()
        for output in trial.outputs.values():
            if isinstance(output, ResourceRef):
                yield output
        for metric in trial.metrics.values():
            if metric.spec is not None and metric.spec.ref is not None:
                yield metric.spec.ref


def _bridge_headers(token_env: str, *, dependency_capability: str | None = None) -> dict[str, str]:
    """Send a host token locally or an OpenShell-managed opaque placeholder."""
    token = os.environ.get(token_env)
    if not token:
        raise DependencyRuntimeError(f"Missing bridge token environment variable {token_env}")
    headers = {"Authorization": f"Bearer {token}"}
    if dependency_capability is not None:
        headers["X-Nemo-Dependency-Capability"] = dependency_capability
    return headers


class RemoteHarborEvaluatorConfig(HarborEvaluatorConfig):
    """Sandbox-side transport settings; resource authority stays server-side."""

    model_config = ConfigDict(extra="forbid")

    bridge_url: AnyHttpUrl
    bridge_token_env: str = BRIDGE_TOKEN_ENV
    run_profile: Literal["smoke", "standard"] = "standard"
    poll_interval_sec: float = Field(default=1.0, ge=0.01, le=30)
    request_timeout_sec: float = Field(default=60.0, ge=1, le=600)
    evaluation_timeout_sec: float = Field(default=7200.0, ge=1, le=86_400)
    max_archive_bytes: int = Field(default=512 * 1024 * 1024, ge=1)


class RemoteHarborDependencyRuntime(DependencyRuntime):
    """Opaque bridge-backed task environment."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    base_task_id: str
    envelope_id: str
    envelope_digest: str
    task_path: Path
    overlay_policy: TaskEnvelopePolicy
    bridge_url: AnyHttpUrl
    bridge_token_env: str = BRIDGE_TOKEN_ENV
    request_timeout_sec: float = 60.0
    max_archive_bytes: int = Field(default=512 * 1024 * 1024, ge=1)

    _session_id: str | None = PrivateAttr(default=None)
    _capability: str | None = PrivateAttr(default=None)
    _transport: httpx.AsyncBaseTransport | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def reject_local_lifecycle(self) -> RemoteHarborDependencyRuntime:
        """Keep dependency lifecycle commands behind the bridge."""
        if self.start is not None or self.readiness is not None or self.stop is not None:
            raise ValueError("Remote Harbor dependencies do not accept local lifecycle commands")
        return self

    def context(self) -> RemoteHarborDependencyContext:
        runtime = self.model_copy(deep=False)
        runtime._session_id = None
        runtime._capability = None
        runtime._transport = self._transport
        return RemoteHarborDependencyContext(runtime)

    async def execute(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout: float = 30.0,
    ) -> DependencyCommandResult:
        if self._session_id is None or self._capability is None:
            raise DependencyRuntimeError("Remote Harbor dependency session is not running")
        response = await self._request(
            "POST",
            f"/v1/dependencies/{self._session_id}/exec",
            capability=self._capability,
            json=DependencyExecRequest(
                command=command,
                stdin=stdin,
                timeout_sec=max(1, int(timeout)),
            ).model_dump(),
        )
        if response.status_code != 200:
            raise DependencyRuntimeError(f"Harbor dependency command failed with HTTP {response.status_code}")
        result = DependencyExecResponse.model_validate_json(response.content)
        return DependencyCommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        capability: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = _bridge_headers(self.bridge_token_env, dependency_capability=capability)
        async with httpx.AsyncClient(timeout=self.request_timeout_sec, transport=self._transport) as client:
            return await client.request(
                method,
                f"{str(self.bridge_url).rstrip('/')}{path}",
                headers=headers,
                **kwargs,
            )


class RemoteHarborDependencyContext:
    def __init__(self, runtime: RemoteHarborDependencyRuntime) -> None:
        self.runtime = runtime

    async def __aenter__(self) -> DependencyRuntime:
        binding = ResolvedEnvelopeTask(
            envelope_id=self.runtime.envelope_id,
            envelope_digest=self.runtime.envelope_digest,
            task_id=self.runtime.task_id,
            base_task_id=self.runtime.base_task_id,
            task_path=self.runtime.task_path,
            policy=self.runtime.overlay_policy,
        )
        root = Path.cwd() / "tmp" / "harbor-bridge" / f"dependency-{uuid4().hex}"
        overlay_dir = root / "overlay"
        archive = root / "overlay.tar.gz"
        root.mkdir(parents=True)
        try:
            digest = create_overlay_directory([binding], overlay_dir)
            metadata = DependencyStartRequest(
                request_id=f"dependency-{uuid4().hex[:16]}",
                envelope_id=binding.envelope_id,
                envelope_digest=binding.envelope_digest,
                task_id=binding.task_id,
                base_task_id=binding.base_task_id,
                overlay_digest=digest,
            )
            files = None
            handle = None
            if digest is not None:
                create_directory_archive(
                    overlay_dir,
                    archive,
                    max_bytes=self.runtime.max_archive_bytes,
                )
                handle = archive.open("rb")
                files = {"overlay": ("overlay.tar.gz", handle, "application/gzip")}
            try:
                response = await self.runtime._request(
                    "POST",
                    "/v1/dependencies",
                    data={"metadata": metadata.model_dump_json()},
                    files=files,
                )
            finally:
                if handle is not None:
                    handle.close()
            if response.status_code != 201:
                raise DependencyRuntimeError(f"Harbor dependency startup failed with HTTP {response.status_code}")
            session = DependencySession.model_validate_json(response.content)
            self.runtime._session_id = session.session_id
            self.runtime._capability = session.capability_token
            return self.runtime
        finally:
            shutil.rmtree(root, ignore_errors=True)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, traceback
        shutdown_error: Exception | None = None
        try:
            if self.runtime._session_id is not None and self.runtime._capability is not None:
                response = await self.runtime._request(
                    "DELETE",
                    f"/v1/dependencies/{self.runtime._session_id}",
                    capability=self.runtime._capability,
                )
                if response.status_code != 204:
                    shutdown_error = DependencyRuntimeError(
                        f"Harbor dependency shutdown failed with HTTP {response.status_code}"
                    )
        except Exception as error:
            shutdown_error = error
        finally:
            self.runtime._session_id = None
            self.runtime._capability = None
        if shutdown_error is not None:
            if exc is None:
                raise shutdown_error
            logger.warning(
                "Harbor dependency shutdown failed while preserving the active body exception",
                exc_info=(type(shutdown_error), shutdown_error, shutdown_error.__traceback__),
            )
        return False


class RemoteHarborEvaluator(Evaluator):
    """Submit inert candidate/overlay archives and poll the bounded bridge."""

    evaluator_type: EvaluatorType = "harbor"

    def __init__(
        self,
        options: RemoteHarborEvaluatorConfig,
        experiment_dir: Path | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(options, experiment_dir)
        self._transport = transport

    def prepare_dataset(self, dataset: Dataset) -> Dataset:
        if not isinstance(dataset, HarborDataset) or dataset.source is None:
            raise ValueError("Remote Harbor evaluator requires a sourced Harbor dataset")
        root = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()
        options = self.options
        assert isinstance(options, RemoteHarborEvaluatorConfig)
        for task in dataset.tasks:
            if isinstance(task.dependencies, RemoteHarborDependencyRuntime):
                continue
            if not isinstance(task.dependencies, HarborDependencyRuntime):
                raise DependencyRuntimeError(
                    f"Remote Harbor evaluator will not run unsupported task dependencies locally: {task.id}"
                )
            task_path = local_path_from_uri(task.uri, context="Harbor task reference").resolve()
            binding = resolve_envelope_task(root, task_path, task_id=task.id)
            runtime = RemoteHarborDependencyRuntime.model_validate(
                {
                    "task_id": task.id,
                    "base_task_id": binding.base_task_id,
                    "envelope_id": binding.envelope_id,
                    "envelope_digest": binding.envelope_digest,
                    "task_path": task_path,
                    "overlay_policy": binding.policy,
                    "bridge_url": options.bridge_url,
                    "bridge_token_env": options.bridge_token_env,
                    "request_timeout_sec": options.request_timeout_sec,
                    "max_archive_bytes": options.max_archive_bytes,
                }
            )
            runtime._transport = self._transport
            task.dependencies = runtime
        return dataset

    async def _materialize_result_artifacts(
        self,
        client: httpx.AsyncClient,
        *,
        job_id: str,
        result: EvaluationResult,
        headers: dict[str, str],
        staging: Path,
        options: RemoteHarborEvaluatorConfig,
    ) -> None:
        archive = staging / "result-artifacts.tar.gz"
        total = 0
        async with client.stream(
            "GET",
            f"{str(options.bridge_url).rstrip('/')}/v1/evaluations/{job_id}/artifacts",
            headers=headers,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Harbor bridge artifact download failed with HTTP {response.status_code}")
            expected_digest = response.headers.get("X-Nemo-Artifact-Digest")
            if expected_digest is None:
                raise RuntimeError("Harbor bridge artifact response omitted its digest")
            with archive.open("xb") as output:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > options.max_archive_bytes:
                        raise RuntimeError("Harbor bridge artifact archive exceeds the configured limit")
                    output.write(chunk)

        artifact_root = (self.experiment_dir or Path.cwd()) / "remote-harbor-artifacts" / job_id
        extract_directory_archive(
            archive,
            artifact_root,
            max_bytes=options.max_archive_bytes,
        )
        if transport_tree_digest(artifact_root) != expected_digest:
            shutil.rmtree(artifact_root, ignore_errors=True)
            raise RuntimeError("Harbor bridge artifact digest mismatch")

        for resource in _result_resource_refs(result):
            parsed = urlparse(resource.uri)
            if parsed.scheme != "nemo-harbor-bridge" or not parsed.path.startswith("/artifacts/"):
                continue
            relative = unquote(parsed.path.removeprefix("/artifacts/"))
            local = (artifact_root / relative).resolve()
            if not local.is_relative_to(artifact_root) or not local.exists():
                raise RuntimeError("Harbor bridge result references a missing or unsafe artifact")
            resource.uri = local.as_uri()

    async def _run(
        self,
        agent: Path,
        dataset: Dataset,
        options: EvaluatorConfig,
    ) -> Sequence[TrialResult]:
        if not isinstance(options, RemoteHarborEvaluatorConfig):
            raise TypeError("Remote Harbor evaluator requires RemoteHarborEvaluatorConfig")
        if not isinstance(dataset, HarborDataset) or dataset.source is None:
            raise ValueError("Dataset must be a sourced Harbor dataset")
        root = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()
        bindings = [
            resolve_envelope_task(
                root,
                local_path_from_uri(task.uri, context="Harbor task reference").resolve(),
                task_id=task.id,
            )
            for task in dataset.tasks
        ]
        identities = {(item.envelope_id, item.envelope_digest) for item in bindings}
        if len(identities) != 1:
            raise ValueError("One evaluation may reference exactly one trusted task envelope")
        envelope_id, envelope_digest = identities.pop()
        headers = _bridge_headers(options.bridge_token_env)

        staging = (self.experiment_dir or Path.cwd()) / "tmp" / "harbor-bridge" / uuid4().hex
        staging.mkdir(parents=True)
        candidate_archive = staging / "candidate.tar.gz"
        overlay_dir = staging / "overlay"
        overlay_archive = staging / "overlay.tar.gz"
        job_id = None
        try:
            create_directory_archive(agent, candidate_archive, max_bytes=options.max_archive_bytes)
            overlay_digest = create_overlay_directory(bindings, overlay_dir)
            if overlay_digest is not None:
                create_directory_archive(overlay_dir, overlay_archive, max_bytes=options.max_archive_bytes)
            submission = EvaluationSubmission(
                request_id=f"{agent.name}-{uuid4().hex[:12]}",
                envelope=EvaluationEnvelope(
                    id=envelope_id,
                    digest=envelope_digest,
                    tasks=[EnvelopeTask(task_id=item.task_id, base_task_id=item.base_task_id) for item in bindings],
                ),
                candidate=ArchiveReference(digest=transport_tree_digest(agent)),
                overlay=ArchiveReference(digest=overlay_digest) if overlay_digest is not None else None,
                run_profile=options.run_profile,
            )
            async with httpx.AsyncClient(
                timeout=options.request_timeout_sec,
                transport=self._transport,
            ) as client:
                candidate_handle = candidate_archive.open("rb")
                overlay_handle = overlay_archive.open("rb") if overlay_digest is not None else None
                files = {"candidate": ("candidate.tar.gz", candidate_handle, "application/gzip")}
                if overlay_handle is not None:
                    files["overlay"] = ("overlay.tar.gz", overlay_handle, "application/gzip")
                try:
                    response = await client.post(
                        f"{str(options.bridge_url).rstrip('/')}/v1/evaluations",
                        headers=headers,
                        data={"metadata": submission.model_dump_json()},
                        files=files,
                    )
                finally:
                    candidate_handle.close()
                    if overlay_handle is not None:
                        overlay_handle.close()
                if response.status_code != 202:
                    raise RuntimeError(f"Harbor bridge submission failed with HTTP {response.status_code}")
                accepted = EvaluationAccepted.model_validate_json(response.content)
                job_id = accepted.job_id
                deadline = asyncio.get_running_loop().time() + options.evaluation_timeout_sec
                while True:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise TimeoutError("Harbor bridge evaluation timed out")
                    response = await client.get(
                        f"{str(options.bridge_url).rstrip('/')}/v1/evaluations/{job_id}",
                        headers=headers,
                    )
                    if response.status_code != 200:
                        raise RuntimeError(f"Harbor bridge polling failed with HTTP {response.status_code}")
                    status = EvaluationStatus.model_validate_json(response.content)
                    if status.state == EvaluationState.COMPLETED:
                        assert status.result is not None
                        await self._materialize_result_artifacts(
                            client,
                            job_id=job_id,
                            result=status.result,
                            headers=headers,
                            staging=staging,
                            options=options,
                        )
                        return list(status.result.trials)
                    if status.state in (EvaluationState.FAILED, EvaluationState.CANCELLED):
                        raise RuntimeError(status.error or f"Harbor bridge evaluation {status.state}")
                    await asyncio.sleep(options.poll_interval_sec)
        except asyncio.CancelledError:
            if job_id is not None:
                async with httpx.AsyncClient(
                    timeout=options.request_timeout_sec,
                    transport=self._transport,
                ) as client:
                    await client.delete(
                        f"{str(options.bridge_url).rstrip('/')}/v1/evaluations/{job_id}",
                        headers=headers,
                    )
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def remote_dependency_runtime_for_task(task_dir: Path, *, task_id: str) -> RemoteHarborDependencyRuntime:
    """Bind a freshly materialized task to the bridge before analyzer use."""
    bridge_url = os.environ.get(BRIDGE_URL_ENV)
    if not bridge_url:
        raise DependencyRuntimeError(f"{BRIDGE_URL_ENV} is required inside the OpenShell runtime")
    binding = resolve_envelope_task(task_dir.parent, task_dir, task_id=task_id)
    return RemoteHarborDependencyRuntime.model_validate(
        {
            "task_id": task_id,
            "base_task_id": binding.base_task_id,
            "envelope_id": binding.envelope_id,
            "envelope_digest": binding.envelope_digest,
            "task_path": task_dir,
            "overlay_policy": binding.policy,
            "bridge_url": bridge_url,
        }
    )
