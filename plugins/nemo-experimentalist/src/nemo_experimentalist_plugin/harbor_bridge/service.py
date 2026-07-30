# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authenticated local FastAPI boundary around trusted Harbor execution."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Protocol
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import EvaluationResult
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    create_result_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    HarborBridgeRequest,
    HarborDependencyExecRequest,
    HarborDependencyExecResponse,
    HarborDependencyRequest,
    HarborDependencySessionResponse,
)
from nemo_experimentalist_plugin.harbor_bridge.dependencies import (
    HarborDependencyCapacityError,
    HarborDependencySessionManager,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    EnvelopeTaskSelection,
    TrustedEnvelopeCatalog,
    tree_digest,
)
from nemo_experimentalist_plugin.harbor_bridge.runner import HarborBridgeRunner
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.background import BackgroundTask
from starlette.datastructures import FormData, UploadFile

logger = logging.getLogger(__name__)


class EvaluationRunner(Protocol):
    """Trusted implementation seam used by the HTTP boundary."""

    async def run(
        self,
        request: HarborBridgeRequest,
        *,
        candidate_dir: Path,
        dataset_dir: Path,
        work_dir: Path,
    ) -> EvaluationResult: ...


class DependencySessionRunner(Protocol):
    """Trusted seam for bridge-owned task dependency environments."""

    async def start(self, request: HarborDependencyRequest, *, task_dir: Path) -> str: ...

    async def execute(
        self,
        session_id: str,
        request: HarborDependencyExecRequest,
    ) -> HarborDependencyExecResponse: ...

    async def stop(self, session_id: str) -> None: ...

    async def close(self) -> None: ...


class HarborBridgeSettings(BaseModel):
    """Local service limits and storage configuration."""

    model_config = ConfigDict(extra="forbid")

    storage_root: Path
    catalog_root: Path
    token: str = Field(min_length=16)
    max_archive_bytes: int = Field(default=DEFAULT_MAX_ARCHIVE_BYTES, ge=1, le=2 * 1024 * 1024 * 1024)
    max_concurrent_requests: int = Field(default=1, ge=1, le=8)
    max_concurrent_dependency_sessions: int = Field(default=8, ge=1, le=64)


async def _save_upload(upload: UploadFile, destination: Path, *, max_bytes: int) -> None:
    if upload.content_type not in ("application/gzip", "application/x-gzip", "application/octet-stream"):
        raise HTTPException(status_code=415, detail=f"Unsupported archive content type: {upload.content_type}")
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Archive exceeds {max_bytes} bytes")
                output.write(chunk)
    finally:
        await upload.close()


async def _require_form_parts(
    request: Request,
    *,
    required: set[str],
    optional: set[str],
) -> FormData:
    """Reject legacy or duplicate multipart authorities explicitly."""
    form = await request.form()
    keys = [key for key, _value in form.multi_items()]
    allowed = required | optional
    unexpected = sorted(set(keys) - allowed)
    if unexpected:
        raise HTTPException(status_code=422, detail=f"Unexpected multipart field(s): {', '.join(unexpected)}")
    missing = sorted(required - set(keys))
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing multipart field(s): {', '.join(missing)}")
    duplicated = sorted(key for key in allowed if keys.count(key) > 1)
    if duplicated:
        raise HTTPException(status_code=422, detail=f"Duplicate multipart field(s): {', '.join(duplicated)}")
    return form


def create_app(
    *,
    settings: HarborBridgeSettings,
    runner: EvaluationRunner | None = None,
    dependency_sessions: DependencySessionRunner | None = None,
    catalog: TrustedEnvelopeCatalog | None = None,
) -> FastAPI:
    """Build the local-only bridge application."""
    service_runner = runner or HarborBridgeRunner()
    session_runner = dependency_sessions or HarborDependencySessionManager(
        max_concurrent_sessions=settings.max_concurrent_dependency_sessions
    )
    dependency_work_dirs: dict[str, Path] = {}
    dependency_capabilities: dict[str, str] = {}
    trusted_catalog = catalog or TrustedEnvelopeCatalog(settings.catalog_root)
    sealed_scorers: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[str, str | None]] = {}
    storage_root = settings.storage_root.expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            try:
                await session_runner.close()
            finally:
                for work_dir in dependency_work_dirs.values():
                    shutil.rmtree(work_dir, ignore_errors=True)
                dependency_work_dirs.clear()
                dependency_capabilities.clear()

    app = FastAPI(
        title="NeMo Experimentalist Harbor Bridge",
        description="Narrow research-preview boundary around trusted Harbor execution.",
        version="0.1.0",
        lifespan=lifespan,
    )
    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {settings.token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid Harbor bridge bearer token")

    def authorize_dependency_session(session_id: str, capability: str | None) -> None:
        expected = dependency_capabilities.get(session_id)
        if expected is None:
            raise HTTPException(status_code=404, detail="Harbor dependency session not found")
        if capability is None or not secrets.compare_digest(capability, expected):
            raise HTTPException(status_code=403, detail="Invalid Harbor dependency session capability")

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/v1/evaluations",
        response_class=FileResponse,
        dependencies=[Depends(authorize)],
    )
    async def evaluate(raw_request: Request) -> FileResponse:
        form = await _require_form_parts(
            raw_request,
            required={"request", "candidate"},
            optional={"overlay"},
        )
        request = form["request"]
        candidate = form["candidate"]
        overlay = form.get("overlay")
        if not isinstance(request, str):
            raise HTTPException(status_code=422, detail="Multipart request field must be text")
        if not isinstance(candidate, UploadFile):
            raise HTTPException(status_code=422, detail="Multipart candidate field must be a file")
        if overlay is not None and not isinstance(overlay, UploadFile):
            raise HTTPException(status_code=422, detail="Multipart overlay field must be a file")
        try:
            bridge_request = HarborBridgeRequest.model_validate_json(request)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

        work_dir = storage_root / f"{bridge_request.request_id}-{uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=False)
        candidate_archive = work_dir / "candidate.tar.gz"
        overlay_archive = work_dir / "overlay.tar.gz"
        candidate_dir = work_dir / "candidate"
        overlay_dir = work_dir / "overlay"
        dataset_dir = work_dir / "dataset"
        response_archive = work_dir / "response.tar.gz"
        try:
            await _save_upload(candidate, candidate_archive, max_bytes=settings.max_archive_bytes)
            extract_directory_archive(
                candidate_archive,
                candidate_dir,
                max_bytes=settings.max_archive_bytes,
            )
            if tree_digest(candidate_dir) != bridge_request.candidate_digest:
                raise HTTPException(status_code=422, detail="Candidate content digest does not match request")
            if overlay is None and bridge_request.overlay_digest is not None:
                raise HTTPException(status_code=422, detail="Task overlay archive is missing")
            if overlay is not None and bridge_request.overlay_digest is None:
                raise HTTPException(status_code=422, detail="Unexpected task overlay archive")
            if overlay is not None:
                await _save_upload(overlay, overlay_archive, max_bytes=settings.max_archive_bytes)
                extract_directory_archive(
                    overlay_archive,
                    overlay_dir,
                    max_bytes=settings.max_archive_bytes,
                )
                if tree_digest(overlay_dir) != bridge_request.overlay_digest:
                    raise HTTPException(status_code=422, detail="Task overlay content digest does not match request")

            trusted_catalog.materialize(
                envelope_id=bridge_request.envelope_id,
                envelope_digest=bridge_request.envelope_digest,
                selections=bridge_request.tasks,
                destination=dataset_dir,
                overlay_dir=overlay_dir if overlay is not None else None,
            )
            if bridge_request.scorer_identity is not None:
                scorer_key = (
                    bridge_request.envelope_id,
                    tuple((task.task_id, task.base_task_id) for task in bridge_request.tasks),
                )
                scorer_value = (bridge_request.scorer_identity, bridge_request.overlay_digest)
                sealed = sealed_scorers.setdefault(scorer_key, scorer_value)
                if sealed != scorer_value:
                    raise HTTPException(
                        status_code=409,
                        detail="Insight scorer is already sealed for this trusted task selection",
                    )
            async with semaphore:
                result = await service_runner.run(
                    bridge_request,
                    candidate_dir=candidate_dir,
                    dataset_dir=dataset_dir,
                    work_dir=work_dir,
                )
            result.metadata.update(
                {
                    "trusted_envelope_id": bridge_request.envelope_id,
                    "trusted_envelope_digest": bridge_request.envelope_digest,
                    "candidate_digest": bridge_request.candidate_digest,
                    "task_overlay_digest": bridge_request.overlay_digest or "",
                    "scorer_identity": bridge_request.scorer_identity or "",
                }
            )
            create_result_archive(
                result,
                work_dir / "results",
                response_archive,
                additional_resource_roots={"dataset": dataset_dir},
                max_bytes=settings.max_archive_bytes,
            )
            if response_archive.stat().st_size > settings.max_archive_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Evaluation result exceeds {settings.max_archive_bytes} bytes",
                )
            return FileResponse(
                response_archive,
                media_type="application/gzip",
                filename=f"{bridge_request.request_id}.tar.gz",
                background=BackgroundTask(shutil.rmtree, work_dir, ignore_errors=True),
            )
        except HTTPException:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except (KeyError, ValueError) as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except asyncio.CancelledError:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.exception("Harbor bridge evaluation failed")
            raise HTTPException(status_code=500, detail="Harbor evaluation failed") from exc

    @app.post(
        "/v1/dependencies",
        response_model=HarborDependencySessionResponse,
        status_code=201,
        dependencies=[Depends(authorize)],
    )
    async def start_dependency(raw_request: Request) -> HarborDependencySessionResponse:
        form = await _require_form_parts(
            raw_request,
            required={"request"},
            optional={"overlay"},
        )
        request = form["request"]
        overlay = form.get("overlay")
        if not isinstance(request, str):
            raise HTTPException(status_code=422, detail="Multipart request field must be text")
        if overlay is not None and not isinstance(overlay, UploadFile):
            raise HTTPException(status_code=422, detail="Multipart overlay field must be a file")
        try:
            dependency_request = HarborDependencyRequest.model_validate_json(request)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

        work_dir = storage_root / f"dependency-{dependency_request.request_id}-{uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=False)
        overlay_archive = work_dir / "overlay.tar.gz"
        overlay_dir = work_dir / "overlay"
        task_dir = work_dir / "task" / dependency_request.task_id
        try:
            if overlay is None and dependency_request.overlay_digest is not None:
                raise HTTPException(status_code=422, detail="Task overlay archive is missing")
            if overlay is not None and dependency_request.overlay_digest is None:
                raise HTTPException(status_code=422, detail="Unexpected task overlay archive")
            if overlay is not None:
                await _save_upload(overlay, overlay_archive, max_bytes=settings.max_archive_bytes)
                extract_directory_archive(
                    overlay_archive,
                    overlay_dir,
                    max_bytes=settings.max_archive_bytes,
                )
                if tree_digest(overlay_dir) != dependency_request.overlay_digest:
                    raise HTTPException(status_code=422, detail="Task overlay content digest does not match request")
            materialized_root = work_dir / "task"
            trusted_catalog.materialize(
                envelope_id=dependency_request.envelope_id,
                envelope_digest=dependency_request.envelope_digest,
                selections=[
                    EnvelopeTaskSelection(
                        task_id=dependency_request.task_id,
                        base_task_id=dependency_request.base_task_id,
                    )
                ],
                destination=materialized_root,
                overlay_dir=overlay_dir if overlay is not None else None,
            )
            session_id = await session_runner.start(
                dependency_request,
                task_dir=task_dir,
            )
            dependency_work_dirs[session_id] = work_dir
            capability_token = secrets.token_urlsafe(32)
            dependency_capabilities[session_id] = capability_token
            return HarborDependencySessionResponse(
                session_id=session_id,
                capability_token=capability_token,
            )
        except HarborDependencyCapacityError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except HTTPException:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except (KeyError, ValueError) as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except asyncio.CancelledError:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.exception("Harbor dependency startup failed")
            raise HTTPException(status_code=500, detail="Harbor dependency startup failed") from exc

    @app.post(
        "/v1/dependencies/{session_id}/exec",
        response_model=HarborDependencyExecResponse,
        dependencies=[Depends(authorize)],
    )
    async def execute_dependency(
        session_id: str,
        request: HarborDependencyExecRequest,
        capability: Annotated[str | None, Header(alias="X-Nemo-Dependency-Capability")] = None,
    ) -> HarborDependencyExecResponse:
        authorize_dependency_session(session_id, capability)
        try:
            return await session_runner.execute(session_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Harbor dependency session not found") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Harbor dependency command failed")
            raise HTTPException(status_code=500, detail="Harbor dependency command failed") from exc

    @app.delete(
        "/v1/dependencies/{session_id}",
        status_code=204,
        dependencies=[Depends(authorize)],
    )
    async def stop_dependency(
        session_id: str,
        capability: Annotated[str | None, Header(alias="X-Nemo-Dependency-Capability")] = None,
    ) -> None:
        authorize_dependency_session(session_id, capability)
        work_dir = dependency_work_dirs.get(session_id)
        try:
            await session_runner.stop(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Harbor dependency session not found") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Harbor dependency shutdown failed")
            raise HTTPException(status_code=500, detail="Harbor dependency shutdown failed") from exc
        finally:
            dependency_work_dirs.pop(session_id, None)
            dependency_capabilities.pop(session_id, None)
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)

    return app


def main() -> None:
    """Run the local research-preview bridge."""
    parser = argparse.ArgumentParser(description="Run the NeMo Experimentalist Harbor bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--storage-root", type=Path, default=Path.cwd() / "tmp" / "experimentalist-harbor-bridge")
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--token-env", default="NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN")
    parser.add_argument("--max-archive-bytes", type=int, default=DEFAULT_MAX_ARCHIVE_BYTES)
    parser.add_argument("--max-dependency-sessions", type=int, default=8)
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"Harbor bridge token environment variable is not set: {args.token_env}")
    settings = HarborBridgeSettings(
        storage_root=args.storage_root,
        catalog_root=args.catalog_root,
        token=token,
        max_archive_bytes=args.max_archive_bytes,
        max_concurrent_dependency_sessions=args.max_dependency_sessions,
    )
    uvicorn.run(create_app(settings=settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
