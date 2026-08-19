# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ephemeral, authenticated, job-shaped Harbor bridge."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import logging
import os
import shutil
import stat
import tarfile
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol
from urllib.parse import unquote, urlparse
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from nemo_experimentalist_plugin.entities import (
    DataValue,
    EvaluationResult,
    ResourceRef,
)
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    DEFAULT_MAX_ARCHIVE_FILES,
    create_directory_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    BridgeRuntimeConfig,
    DependencyExecRequest,
    DependencyExecResponse,
    DependencySession,
    DependencyStartRequest,
    EnvelopeTask,
    EvaluationAccepted,
    EvaluationState,
    EvaluationStatus,
    EvaluationSubmission,
    RunProfile,
)
from nemo_experimentalist_plugin.harbor_bridge.dependencies import HarborDependencySessionManager
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    TrustedEnvelopeCatalog,
    transport_tree_digest,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import FormData, UploadFile
from starlette.responses import FileResponse

logger = logging.getLogger(__name__)


RUN_PROFILES: dict[Literal["smoke", "standard"], RunProfile] = {
    "smoke": RunProfile(
        attempts=1,
        concurrency=1,
        retries=0,
        agent_timeout_multiplier=0.25,
        verifier_timeout_multiplier=0.25,
        setup_timeout_multiplier=0.5,
        build_timeout_multiplier=0.5,
    ),
    "standard": RunProfile(
        attempts=3,
        concurrency=4,
        retries=1,
        agent_timeout_multiplier=1.0,
        verifier_timeout_multiplier=1.0,
        setup_timeout_multiplier=1.0,
        build_timeout_multiplier=1.0,
    ),
}


class HarborBridgeSettings(BaseModel):
    """Trusted bridge startup settings unavailable to OpenShell."""

    model_config = ConfigDict(extra="forbid")

    storage_root: Path
    catalog_root: Path
    token: str = Field(min_length=16)
    max_archive_bytes: int = Field(default=DEFAULT_MAX_ARCHIVE_BYTES, ge=1, le=2 * 1024 * 1024 * 1024)
    max_archive_files: int = Field(default=DEFAULT_MAX_ARCHIVE_FILES, ge=1, le=100_000)
    max_concurrent_evaluations: int = Field(default=1, ge=1, le=8)
    max_concurrent_dependency_sessions: int = Field(default=2, ge=1, le=8)
    standard_attempts: int = Field(default=3, ge=1, le=3)
    standard_concurrency: int = Field(default=os.cpu_count() or 4, ge=1)
    sensitive_values: tuple[str, ...] = ()


class EvaluationRunner(Protocol):
    """Trusted adapter from validated bridge state to Harbor."""

    async def run(
        self,
        *,
        submission: EvaluationSubmission,
        profile: RunProfile,
        candidate_dir: Path,
        dataset_dir: Path,
        work_dir: Path,
    ) -> EvaluationResult:
        """Execute a fully server-constructed Harbor job."""
        ...


class UnconfiguredRunner:
    """Fail loudly until the trusted Harbor runner is wired."""

    async def run(
        self,
        *,
        submission: EvaluationSubmission,
        profile: RunProfile,
        candidate_dir: Path,
        dataset_dir: Path,
        work_dir: Path,
    ) -> EvaluationResult:
        del submission, profile, candidate_dir, dataset_dir, work_dir
        raise RuntimeError("Trusted Harbor runner is not configured")


@dataclass
class _Job:
    job_id: str
    work_dir: Path
    state: EvaluationState = EvaluationState.PENDING
    result: EvaluationResult | None = None
    error: str | None = None
    artifact_archive: Path | None = None
    artifact_digest: str | None = None
    task: asyncio.Task[None] | None = None

    def status(self) -> EvaluationStatus:
        return EvaluationStatus(
            job_id=self.job_id,
            state=self.state,
            result=self.result,
            error=self.error,
        )


async def _require_form_parts(
    request: Request,
    *,
    required: set[str],
    optional: set[str],
) -> FormData:
    form = await request.form()
    keys = [key for key, _value in form.multi_items()]
    allowed = required | optional
    unexpected = sorted(set(keys) - allowed)
    missing = sorted(required - set(keys))
    duplicated = sorted(key for key in allowed if keys.count(key) > 1)
    if unexpected or missing or duplicated:
        raise HTTPException(status_code=422, detail="Invalid multipart evaluation request")
    return form


async def _save_upload(upload: UploadFile, destination: Path, *, max_bytes: int) -> None:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Compressed archive exceeds bridge limit")
                output.write(chunk)
    finally:
        await upload.close()


def _resource_refs(result: EvaluationResult) -> Iterator[ResourceRef]:
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


def _redact_value(value: DataValue, sensitive: tuple[str, ...]) -> DataValue:
    if isinstance(value, str):
        redacted = value
        for secret in sensitive:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        if redacted.startswith("/") or urlparse(redacted).scheme == "file":
            return "[HOST_PATH_REDACTED]"
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, sensitive) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, sensitive) for key, item in value.items()}
    return value


def _constant_time_equal(value: str, expected: str) -> bool:
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def _copy_result_resource(
    source: Path,
    destination: Path,
    *,
    scratch: Path,
    max_bytes: int,
    max_files: int,
) -> Path:
    """Copy one result-owned resource into the export tree without links.

    Regular files are copied directly. Directories make a safe archive/extract
    round trip, which reuses the same link, special-file, traversal, count, and
    byte-limit checks enforced for bridge transport archives.

    Args:
        source: Result-owned file or directory below the bridge job directory.
        destination: Export-tree location for the copied resource.
        scratch: Temporary directory for directory archive round trips.
        max_bytes: Maximum bytes permitted for one resource tree.
        max_files: Maximum entries permitted for one resource tree.

    Returns:
        The copied resource path under ``destination``.

    Raises:
        ValueError: If the resource is a link, special file, or exceeds a limit.
    """
    mode = source.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError("Harbor result resource must not be a symbolic link")
    if stat.S_ISREG(mode):
        if source.stat().st_nlink > 1:
            raise ValueError("Harbor result resource must not be hard linked")
        if source.stat().st_size > max_bytes:
            raise ValueError("Harbor result resource exceeds the bridge artifact limit")
        target = destination / source.name
        destination.mkdir(parents=True)
        shutil.copy2(source, target)
        return target
    if not stat.S_ISDIR(mode):
        raise ValueError("Harbor result resource must be a regular file or directory")
    archive = scratch / f"{destination.name}.tar.gz"
    create_directory_archive(source, archive, max_bytes=max_bytes, max_files=max_files)
    extract_directory_archive(archive, destination, max_bytes=max_bytes, max_files=max_files)
    archive.unlink()
    return destination


def _export_result(
    result: EvaluationResult,
    *,
    job_id: str,
    work_dir: Path,
    sensitive: tuple[str, ...],
    max_bytes: int,
    max_files: int,
) -> tuple[EvaluationResult, Path, str]:
    """Create the only artifact archive that may cross from host to sandbox.

    A result resource is exported only when it resolves below this bridge job's
    ``work_dir`` and is an ordinary file or directory. Its host URI is replaced
    with a bridge-relative URI; all other resource URIs become unavailable.
    The returned result is redacted, while ``artifacts.tar.gz`` contains only
    the copied export tree and its directory-tree digest.

    Args:
        result: Harbor evaluation result before redaction and URI rewriting.
        job_id: Bridge job identifier used only for result ownership context.
        work_dir: Bridge-owned job directory that bounds exportable resources.
        sensitive: Values to redact from result metadata and outputs.
        max_bytes: Maximum bytes permitted in the exported archive tree.
        max_files: Maximum entries permitted in the exported archive tree.

    Returns:
        A redacted result, the gzip-tar artifact path, and its tree digest.

    Raises:
        ValueError: If an otherwise exportable resource is unsafe or exceeds a limit.
    """
    sanitized = EvaluationResult.model_validate_json(result.model_dump_json())
    sanitized.metadata = {key: _redact_value(value, sensitive) for key, value in sanitized.metadata.items()}
    export_root = work_dir / "artifacts-export"
    scratch = work_dir / "artifacts-scratch"
    export_root.mkdir()
    scratch.mkdir()
    for index, resource in enumerate(_resource_refs(sanitized)):
        parsed = urlparse(resource.uri)
        raw_source = Path(unquote(parsed.path)) if parsed.scheme in ("", "file") else None
        source = raw_source.resolve() if raw_source is not None and not raw_source.is_symlink() else None
        if (
            source is not None
            and parsed.netloc in ("", "localhost")
            and source != work_dir
            and source.is_relative_to(work_dir)
            and source.exists()
        ):
            copied = _copy_result_resource(
                source,
                export_root / str(index),
                scratch=scratch,
                max_bytes=max_bytes,
                max_files=max_files,
            )
            relative = copied.relative_to(export_root).as_posix()
            resource.uri = f"nemo-harbor-bridge:///artifacts/{relative}"
        else:
            resource.uri = f"nemo-harbor-bridge:///unavailable/{index}"
        resource.metadata = {key: _redact_value(value, sensitive) for key, value in resource.metadata.items()}
    for trial in sanitized.trials:
        trial.metadata = {key: _redact_value(value, sensitive) for key, value in trial.metadata.items()}
        trial.outputs = {
            key: value if isinstance(value, ResourceRef) else _redact_value(value, sensitive)
            for key, value in trial.outputs.items()
        }
        if trial.error is not None:
            trial.error = {"type": "trial_failed", "message": "See retained Harbor trial logs"}
        for metric in trial.metrics.values():
            metric.metadata = {key: _redact_value(value, sensitive) for key, value in metric.metadata.items()}
    shutil.rmtree(scratch)
    artifact_archive = work_dir / "artifacts.tar.gz"
    create_directory_archive(
        export_root,
        artifact_archive,
        max_bytes=max_bytes,
        max_files=max_files,
    )
    return sanitized, artifact_archive, transport_tree_digest(export_root)


def _validation_detail(exc: ValidationError) -> str:
    locations = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors(include_input=False)})
    return f"Invalid evaluation metadata at: {', '.join(locations[:12])}"


def create_app(
    *,
    settings: HarborBridgeSettings,
    runner: EvaluationRunner | None = None,
    catalog: TrustedEnvelopeCatalog | None = None,
    dependency_sessions: HarborDependencySessionManager | None = None,
) -> FastAPI:
    """Create one run-scoped bridge application."""
    service_runner = runner or UnconfiguredRunner()
    trusted_catalog = catalog or TrustedEnvelopeCatalog(settings.catalog_root)
    storage_root = settings.storage_root.expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    jobs: dict[str, _Job] = {}
    session_manager = dependency_sessions or HarborDependencySessionManager(
        max_concurrent_sessions=settings.max_concurrent_dependency_sessions
    )
    dependency_capabilities: dict[str, str] = {}
    dependency_work_dirs: dict[str, Path] = {}
    semaphore = asyncio.Semaphore(settings.max_concurrent_evaluations)

    async def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {settings.token}"
        if authorization is None or not _constant_time_equal(authorization, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")

    async def execute(job: _Job, submission: EvaluationSubmission) -> None:
        try:
            async with semaphore:
                if job.state == EvaluationState.CANCELLED:
                    return
                job.state = EvaluationState.RUNNING
                profile = RUN_PROFILES[submission.run_profile]
                if submission.run_profile == "standard":
                    profile = profile.model_copy(
                        update={
                            "attempts": settings.standard_attempts,
                            "concurrency": settings.standard_concurrency,
                        }
                    )
                result = await service_runner.run(
                    submission=submission,
                    profile=profile,
                    candidate_dir=job.work_dir / "candidate",
                    dataset_dir=job.work_dir / "dataset",
                    work_dir=job.work_dir,
                )
                job.result, job.artifact_archive, job.artifact_digest = _export_result(
                    result,
                    job_id=job.job_id,
                    work_dir=job.work_dir,
                    sensitive=settings.sensitive_values,
                    max_bytes=settings.max_archive_bytes,
                    max_files=settings.max_archive_files,
                )
                job.state = EvaluationState.COMPLETED
        except asyncio.CancelledError:
            job.state = EvaluationState.CANCELLED
            raise
        except BaseException as exc:
            logger.exception("Harbor bridge job %s failed", job.job_id)
            job.error = f"{type(exc).__name__}: evaluation failed"
            job.state = EvaluationState.FAILED

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            running = [job.task for job in jobs.values() if job.task is not None and not job.task.done()]
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
            await session_manager.close()
            for work_dir in dependency_work_dirs.values():
                shutil.rmtree(work_dir, ignore_errors=True)

    app = FastAPI(
        title="NeMo Experimentalist Harbor Bridge",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/v1/evaluations",
        response_model=EvaluationAccepted,
        status_code=202,
        dependencies=[Depends(require_auth)],
    )
    async def submit_evaluation(request: Request) -> EvaluationAccepted:
        form = await _require_form_parts(
            request,
            required={"metadata", "candidate"},
            optional={"overlay"},
        )
        raw_metadata = form["metadata"]
        candidate_upload = form["candidate"]
        overlay_upload = form.get("overlay")
        if not isinstance(raw_metadata, str) or not isinstance(candidate_upload, UploadFile):
            raise HTTPException(status_code=422, detail="Invalid multipart evaluation request")
        if overlay_upload is not None and not isinstance(overlay_upload, UploadFile):
            raise HTTPException(status_code=422, detail="Invalid multipart evaluation request")
        try:
            submission = EvaluationSubmission.model_validate_json(raw_metadata)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from None
        if (submission.overlay is None) != (overlay_upload is None):
            raise HTTPException(status_code=422, detail="Overlay metadata and archive must be provided together")

        job_id = f"eval-{uuid4().hex}"
        work_dir = storage_root / job_id
        try:
            work_dir.mkdir(exist_ok=False)
            candidate_archive = work_dir / "candidate.tar.gz"
            await _save_upload(candidate_upload, candidate_archive, max_bytes=settings.max_archive_bytes)
            candidate_dir = work_dir / "candidate"
            extract_directory_archive(
                candidate_archive,
                candidate_dir,
                max_bytes=settings.max_archive_bytes,
                max_files=settings.max_archive_files,
            )
            if transport_tree_digest(candidate_dir) != submission.candidate.digest:
                raise ValueError("Candidate archive digest mismatch")

            overlay_dir = None
            if overlay_upload is not None and submission.overlay is not None:
                overlay_archive = work_dir / "overlay.tar.gz"
                await _save_upload(overlay_upload, overlay_archive, max_bytes=settings.max_archive_bytes)
                overlay_dir = work_dir / "overlay"
                extract_directory_archive(
                    overlay_archive,
                    overlay_dir,
                    max_bytes=settings.max_archive_bytes,
                    max_files=settings.max_archive_files,
                )
                if transport_tree_digest(overlay_dir) != submission.overlay.digest:
                    raise ValueError("Overlay archive digest mismatch")

            trusted_catalog.materialize(
                envelope_id=submission.envelope.id,
                envelope_digest=submission.envelope.digest,
                selections=submission.envelope.tasks,
                destination=work_dir / "dataset",
                overlay_dir=overlay_dir,
            )
        except (OSError, KeyError, ValueError, tarfile.TarError):
            logger.exception("Rejected Harbor bridge submission %s", job_id)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail="Evaluation request failed trusted validation") from None

        job = _Job(job_id=job_id, work_dir=work_dir)
        jobs[job_id] = job
        job.task = asyncio.create_task(execute(job, submission), name=f"harbor-bridge-{job_id}")
        return EvaluationAccepted(job_id=job_id)

    @app.get(
        "/v1/evaluations/{job_id}",
        response_model=EvaluationStatus,
        dependencies=[Depends(require_auth)],
    )
    async def get_evaluation(job_id: str) -> EvaluationStatus:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        return job.status()

    @app.get(
        "/v1/evaluations/{job_id}/artifacts",
        dependencies=[Depends(require_auth)],
    )
    async def get_evaluation_artifacts(job_id: str) -> FileResponse:
        """Serve the completed job's approved artifact archive and tree digest.

        This never serves raw Harbor work directories or logs. Only the
        redacted export assembled by :func:`_export_result` is available after
        successful completion, and clients must verify the digest header after
        safe extraction.

        Args:
            job_id: Completed bridge evaluation identifier.

        Returns:
            Gzip-tar response with an ``X-Nemo-Artifact-Digest`` header.

        Raises:
            HTTPException: If the evaluation does not exist or artifacts are not ready.
        """
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        if job.state != EvaluationState.COMPLETED or job.artifact_archive is None or job.artifact_digest is None:
            raise HTTPException(status_code=409, detail="Evaluation artifacts are not ready")
        return FileResponse(
            job.artifact_archive,
            media_type="application/gzip",
            headers={"X-Nemo-Artifact-Digest": job.artifact_digest},
        )

    @app.delete(
        "/v1/evaluations/{job_id}",
        status_code=204,
        dependencies=[Depends(require_auth)],
    )
    async def cancel_evaluation(job_id: str) -> Response:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        if job.task is not None and not job.task.done():
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)
        if job.state in (EvaluationState.PENDING, EvaluationState.RUNNING):
            job.state = EvaluationState.CANCELLED
        return Response(status_code=204)

    @app.post(
        "/v1/dependencies",
        response_model=DependencySession,
        status_code=201,
        dependencies=[Depends(require_auth)],
    )
    async def start_dependency(request: Request) -> DependencySession:
        form = await _require_form_parts(request, required={"metadata"}, optional={"overlay"})
        raw_metadata = form["metadata"]
        overlay_upload = form.get("overlay")
        if not isinstance(raw_metadata, str):
            raise HTTPException(status_code=422, detail="Invalid dependency request")
        if overlay_upload is not None and not isinstance(overlay_upload, UploadFile):
            raise HTTPException(status_code=422, detail="Invalid dependency request")
        try:
            metadata = DependencyStartRequest.model_validate_json(raw_metadata)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc)) from None
        if (metadata.overlay_digest is None) != (overlay_upload is None):
            raise HTTPException(status_code=422, detail="Overlay metadata and archive must be provided together")

        work_dir = storage_root / f"dependency-{uuid4().hex}"
        try:
            work_dir.mkdir()
            overlay_dir = None
            if overlay_upload is not None and metadata.overlay_digest is not None:
                archive = work_dir / "overlay.tar.gz"
                await _save_upload(overlay_upload, archive, max_bytes=settings.max_archive_bytes)
                overlay_dir = work_dir / "overlay"
                extract_directory_archive(
                    archive,
                    overlay_dir,
                    max_bytes=settings.max_archive_bytes,
                    max_files=settings.max_archive_files,
                )
                if transport_tree_digest(overlay_dir) != metadata.overlay_digest:
                    raise ValueError("Overlay digest mismatch")
            dataset_dir = trusted_catalog.materialize(
                envelope_id=metadata.envelope_id,
                envelope_digest=metadata.envelope_digest,
                selections=[EnvelopeTask(task_id=metadata.task_id, base_task_id=metadata.base_task_id)],
                destination=work_dir / "dataset",
                overlay_dir=overlay_dir,
            )
            session_id = await session_manager.start(
                metadata,
                task_dir=dataset_dir / metadata.task_id,
                work_dir=work_dir,
            )
        except (OSError, KeyError, ValueError, RuntimeError, tarfile.TarError):
            logger.exception("Rejected dependency session request")
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail="Dependency request failed trusted validation") from None
        capability = uuid4().hex + uuid4().hex
        dependency_capabilities[session_id] = capability
        dependency_work_dirs[session_id] = work_dir
        return DependencySession(session_id=session_id, capability_token=capability)

    def require_capability(session_id: str, capability: str | None) -> None:
        expected = dependency_capabilities.get(session_id)
        if expected is None:
            raise HTTPException(status_code=404, detail="Dependency session not found")
        if capability is None or not _constant_time_equal(capability, expected):
            raise HTTPException(status_code=403, detail="Invalid dependency capability")

    @app.post(
        "/v1/dependencies/{session_id}/exec",
        response_model=DependencyExecResponse,
        dependencies=[Depends(require_auth)],
    )
    async def execute_dependency(
        session_id: str,
        command: DependencyExecRequest,
        capability: Annotated[str | None, Header(alias="X-Nemo-Dependency-Capability")] = None,
    ) -> DependencyExecResponse:
        require_capability(session_id, capability)
        try:
            return await session_manager.execute(session_id, command)
        except KeyError:
            raise HTTPException(status_code=404, detail="Dependency session not found") from None

    @app.delete(
        "/v1/dependencies/{session_id}",
        status_code=204,
        dependencies=[Depends(require_auth)],
    )
    async def stop_dependency(
        session_id: str,
        capability: Annotated[str | None, Header(alias="X-Nemo-Dependency-Capability")] = None,
    ) -> Response:
        require_capability(session_id, capability)
        try:
            await session_manager.stop(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Dependency session not found") from None
        dependency_capabilities.pop(session_id, None)
        work_dir = dependency_work_dirs.pop(session_id, None)
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
        return Response(status_code=204)

    return app


def main() -> None:
    """Run a bridge from host-provided environment settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path, required=True)
    args = parser.parse_args()
    try:
        runtime_config = BridgeRuntimeConfig.model_validate_json(args.runtime_config.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Could not read bridge runtime configuration: {args.runtime_config}") from exc
    except ValidationError as exc:
        raise SystemExit(f"Invalid bridge runtime configuration: {args.runtime_config}: {exc}") from exc
    token = os.environ.get("NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN")
    if token is None:
        raise SystemExit("NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN is required")
    inference_api_key = os.environ.get("INFERENCE_API_KEY")
    inference_api_base = os.environ.get("INFERENCE_API_BASE")
    aut_model_name = os.environ.get("AUT_MODEL_NAME")
    missing = [
        name
        for name, value in (
            ("INFERENCE_API_KEY", inference_api_key),
            ("INFERENCE_API_BASE", inference_api_base),
            ("AUT_MODEL_NAME", aut_model_name),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Trusted bridge startup environment is missing: {', '.join(missing)}")
    assert inference_api_key is not None
    assert inference_api_base is not None
    assert aut_model_name is not None
    from nemo_experimentalist_plugin.harbor_bridge.runner import (  # noqa: PLC0415
        HarborBridgeRunner,
        TrustedInferenceConfig,
    )

    inference = TrustedInferenceConfig.model_validate(
        {
            "api_key": inference_api_key,
            "api_base": inference_api_base,
            "model_name": aut_model_name,
        }
    )
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=runtime_config.storage_root,
            catalog_root=runtime_config.catalog_root,
            token=token,
            standard_attempts=runtime_config.standard_attempts,
            standard_concurrency=runtime_config.standard_concurrency,
            sensitive_values=(inference_api_key,),
        ),
        runner=HarborBridgeRunner(inference),
    )
    uvicorn.run(app, host=runtime_config.host, port=runtime_config.port, log_level="info")


if __name__ == "__main__":
    main()
