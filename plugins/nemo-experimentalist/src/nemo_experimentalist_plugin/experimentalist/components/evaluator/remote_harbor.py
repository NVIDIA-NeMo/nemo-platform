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
from nemo_experimentalist_plugin.entities import (
    Dataset,
    DatasetRef,
    DependencyCommandResult,
    DependencyRuntime,
    DependencyRuntimeError,
    EvaluationResult,
    ResourceRef,
    Task,
    TrialResult,
    local_path_from_uri,
    subset_dataset_id,
)
from nemo_experimentalist_plugin.experimentalist import roles
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_native import HarborEvaluatorConfig
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
        command_timeout_sec = max(1, int(timeout))
        response = await self._request(
            "POST",
            f"/v1/dependencies/{self._session_id}/exec",
            capability=self._capability,
            json=DependencyExecRequest(
                command=command,
                stdin=stdin,
                timeout_sec=command_timeout_sec,
            ).model_dump(),
            timeout=max(self.request_timeout_sec, command_timeout_sec + 10),
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


class RemoteHarborDataset(HarborDataset):
    """Harbor tasks whose dependency operations are delegated to the bridge.

    The dataset, rather than the evaluator, owns conversion from a task's local
    Harbor dependency declaration to :class:`RemoteHarborDependencyRuntime`.
    Consequently every consumer of the dataset, including a Rationalizer and a
    task subset, sees the bridge-only runtime from the moment the dataset is
    built.
    """

    def __init__(
        self,
        id: str,
        source: ResourceRef | None = None,
        tasks: Sequence[Task] | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        evaluator_config: RemoteHarborEvaluatorConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(id=id, source=source, tasks=tasks, metadata=metadata)
        self._evaluator_config = evaluator_config
        self._transport = transport

    @classmethod
    def from_ref(
        cls,
        ref: DatasetRef,
        *,
        evaluator_config: EvaluatorConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        **options: Any,
    ) -> RemoteHarborDataset:
        """Build a remote Harbor dataset from a local Harbor dataset reference.

        Args:
            ref: Harbor dataset reference.
            evaluator_config: Remote Harbor bridge settings supplied by the
                evaluator factory.
            transport: Optional HTTP transport used for bridge requests. This
                supports in-process bridge tests; production uses the default
                network transport.
            **options: Forwarded to :meth:`HarborDataset.from_ref`.

        Returns:
            A dataset whose task dependencies can only be started through the
            Harbor bridge.
        """
        if not isinstance(evaluator_config, RemoteHarborEvaluatorConfig):
            raise TypeError("Remote Harbor datasets require RemoteHarborEvaluatorConfig")
        return cls.from_harbor_dataset(
            HarborDataset.from_ref(ref, **options),
            evaluator_config=evaluator_config,
            transport=transport,
        )

    @classmethod
    def from_harbor_dataset(
        cls,
        dataset: HarborDataset,
        *,
        evaluator_config: RemoteHarborEvaluatorConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> RemoteHarborDataset:
        """Copy a Harbor dataset and replace each task dependency runtime."""
        if dataset.source is None:
            raise ValueError("Remote Harbor evaluator requires a sourced Harbor dataset")
        root = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()
        return cls(
            id=dataset.id,
            source=dataset.source,
            tasks=[
                cls._remote_task(task, root=root, evaluator_config=evaluator_config, transport=transport)
                for task in dataset.list_tasks()
            ],
            metadata=dataset.metadata,
            evaluator_config=evaluator_config,
            transport=transport,
        )

    @staticmethod
    def _remote_task(
        task,
        *,
        root: Path,
        evaluator_config: RemoteHarborEvaluatorConfig,
        transport: httpx.AsyncBaseTransport | None,
    ) -> Task:
        if isinstance(task.dependencies, RemoteHarborDependencyRuntime):
            runtime = task.dependencies.model_copy(deep=False)
            runtime._transport = transport
            return task.model_copy(update={"dependencies": runtime})
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
                "bridge_url": evaluator_config.bridge_url,
                "bridge_token_env": evaluator_config.bridge_token_env,
                "request_timeout_sec": evaluator_config.request_timeout_sec,
                "max_archive_bytes": evaluator_config.max_archive_bytes,
            }
        )
        runtime._transport = transport
        return task.model_copy(update={"dependencies": runtime})

    def add_tasks(self, tasks: list[Task]) -> None:
        """Add task copies and bind their dependencies to the bridge."""
        super().add_tasks(tasks)
        if self.source is None:
            raise ValueError(f"Remote Harbor dataset {self.id!r} has no source directory")
        root = local_path_from_uri(self.source.uri, context="Harbor dataset reference").resolve()
        self.tasks = [
            self._remote_task(
                task,
                root=root,
                evaluator_config=self._evaluator_config,
                transport=self._transport,
            )
            for task in self.list_tasks()
        ]

    def subset(self, task_ids: Sequence[str]) -> RemoteHarborDataset:
        """Return a bridge-backed subset without reverting to local Docker runtime."""
        selected_ids = set(task_ids)
        tasks = [task for task in self.list_tasks() if task.id in selected_ids]
        missing = selected_ids - {task.id for task in tasks}
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"Task id(s) not found in Remote Harbor dataset {self.id!r}: {missing_text}")
        return RemoteHarborDataset(
            id=subset_dataset_id(self.id, [task.id for task in tasks]),
            source=self.source,
            tasks=tasks,
            metadata=dict(self.metadata),
            evaluator_config=self._evaluator_config,
            transport=self._transport,
        )


class RemoteHarborOutcomeEvaluator(roles.OutcomeEvaluator):
    """Evaluate through the host bridge without giving the sandbox Docker access.

    The sandbox uploads only a candidate source archive and an optional bounded
    task overlay. After Harbor completes on the host, this evaluator downloads
    a separate bridge-approved artifact archive, verifies its directory-tree
    digest, safely extracts it below ``remote-harbor-artifacts/<job-id>``, and
    rewrites result resource URIs to those local extracted files.
    """

    name = "remote-harbor"
    dataset_type = RemoteHarborDataset
    config_type = RemoteHarborEvaluatorConfig
    evaluator_type: EvaluatorType = "remote-harbor"

    def __init__(
        self,
        options: RemoteHarborEvaluatorConfig,
        experiment_dir: Path | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(options, experiment_dir)
        self._transport = transport

    def _result_dir(
        self,
        agent: Path,
        dataset: Dataset,
        options: RemoteHarborEvaluatorConfig,
    ) -> Path:
        """Return the standard, sandbox-owned directory for one evaluation.

        Remote Harbor cannot expose the host's Harbor job directory to the
        sandbox. It must nevertheless honour ``jobs_dir`` so reporters,
        resumptions, and users find remote and native evaluator output in the
        same ``eval-and-optimize/results/<candidate>-<dataset>`` layout.
        """
        jobs_dir = ((self.experiment_dir or Path.cwd()) / options.jobs_dir).resolve()
        result_dir = (jobs_dir / f"{agent.name}-{dataset.id}").resolve()
        if result_dir == jobs_dir or not result_dir.is_relative_to(jobs_dir):
            raise ValueError(f"Remote Harbor result directory escapes jobs_dir: {result_dir}")
        return result_dir

    @staticmethod
    def _write_submission_metadata(result_dir: Path, submission: EvaluationSubmission) -> None:
        """Persist non-secret bridge submission provenance before a remote run.

        The request contract intentionally excludes credentials and host paths,
        so retaining it in the sandbox output is safe. Writing it before the
        POST also makes an interrupted submission inspectable and resumable.
        """
        result_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = result_dir / "metadata.json"
        temporary = result_dir / f".{metadata_path.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(submission.model_dump_json(indent=2) + "\n", encoding="utf-8")
            temporary.replace(metadata_path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _materialize_result_artifacts(
        self,
        client: httpx.AsyncClient,
        *,
        job_id: str,
        result: EvaluationResult,
        headers: dict[str, str],
        staging: Path,
        result_dir: Path,
        options: RemoteHarborEvaluatorConfig,
    ) -> None:
        """Download, verify, extract, and relink approved result artifacts.

        The bridge response includes ``X-Nemo-Artifact-Digest`` for the
        exported directory tree. The archive is size-capped while streaming;
        extraction rejects unsafe tar members; and a post-extraction digest
        mismatch removes the extracted output before reporting failure.

        Args:
            client: Authenticated client connected to the bridge.
            job_id: Completed bridge evaluation identifier.
            result: Sanitized result whose resource URIs are relinked in place.
            headers: Bridge authentication headers.
            staging: Temporary directory for the downloaded archive.
            options: Remote evaluator limits and bridge configuration.

        Raises:
            RuntimeError: If the download, archive validation, digest check, or
                resource URI validation fails.
        """
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

        artifact_root = result_dir / "artifacts"
        shutil.rmtree(artifact_root, ignore_errors=True)
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
        """Upload bounded candidate inputs, poll Harbor, and materialize results.

        ``candidate.tar.gz`` contains only the candidate agent source.
        ``overlay.tar.gz`` is optional and can contain only modifications
        allowed by the trusted task envelope. Neither archive grants the
        sandbox control over Docker, host paths, or the Harbor run profile.

        Args:
            agent: Candidate agent source directory to archive.
            dataset: Harbor dataset constrained by its trusted task envelope.
            options: Remote Harbor evaluator configuration.

        Returns:
            Completed Harbor trial results with local artifact URIs.

        Raises:
            RuntimeError: If bridge submission, polling, or artifact materialization fails.
            TimeoutError: If the bridge evaluation exceeds its configured timeout.
            ValueError: If the dataset violates the trusted envelope contract.
        """
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
        result_dir = self._result_dir(agent, dataset, options)

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
            self._write_submission_metadata(result_dir, submission)
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
                            result_dir=result_dir,
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
