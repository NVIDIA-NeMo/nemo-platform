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
from pathlib import Path
from typing import Annotated, Protocol
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import EvaluationResult
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    create_result_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import HarborBridgeRequest
from nemo_experimentalist_plugin.harbor_bridge.runner import HarborBridgeRunner
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.background import BackgroundTask

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


class HarborBridgeSettings(BaseModel):
    """Local service limits and storage configuration."""

    model_config = ConfigDict(extra="forbid")

    storage_root: Path
    token: str = Field(min_length=16)
    max_archive_bytes: int = Field(default=DEFAULT_MAX_ARCHIVE_BYTES, ge=1, le=2 * 1024 * 1024 * 1024)
    max_concurrent_requests: int = Field(default=1, ge=1, le=8)


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


def create_app(
    *,
    settings: HarborBridgeSettings,
    runner: EvaluationRunner | None = None,
) -> FastAPI:
    """Build the local-only bridge application."""
    app = FastAPI(
        title="NeMo Experimentalist Harbor Bridge",
        description="Narrow research-preview boundary around trusted Harbor execution.",
        version="0.1.0",
    )
    service_runner = runner or HarborBridgeRunner()
    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    storage_root = settings.storage_root.expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {settings.token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid Harbor bridge bearer token")

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/v1/evaluations",
        response_class=FileResponse,
        dependencies=[Depends(authorize)],
    )
    async def evaluate(
        request: Annotated[str, Form()],
        candidate: Annotated[UploadFile, File()],
        dataset: Annotated[UploadFile, File()],
    ) -> FileResponse:
        try:
            bridge_request = HarborBridgeRequest.model_validate_json(request)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

        work_dir = storage_root / f"{bridge_request.request_id}-{uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=False)
        candidate_archive = work_dir / "candidate.tar.gz"
        dataset_archive = work_dir / "dataset.tar.gz"
        candidate_dir = work_dir / "candidate"
        dataset_dir = work_dir / "dataset"
        response_archive = work_dir / "response.tar.gz"
        try:
            await _save_upload(candidate, candidate_archive, max_bytes=settings.max_archive_bytes)
            await _save_upload(dataset, dataset_archive, max_bytes=settings.max_archive_bytes)
            extract_directory_archive(
                candidate_archive,
                candidate_dir,
                max_bytes=settings.max_archive_bytes,
            )
            extract_directory_archive(
                dataset_archive,
                dataset_dir,
                max_bytes=settings.max_archive_bytes,
            )
            async with semaphore:
                result = await service_runner.run(
                    bridge_request,
                    candidate_dir=candidate_dir,
                    dataset_dir=dataset_dir,
                    work_dir=work_dir,
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
        except asyncio.CancelledError:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.exception("Harbor bridge evaluation failed")
            raise HTTPException(status_code=500, detail="Harbor evaluation failed") from exc

    return app


def main() -> None:
    """Run the local research-preview bridge."""
    parser = argparse.ArgumentParser(description="Run the NeMo Experimentalist Harbor bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--storage-root", type=Path, default=Path.cwd() / "tmp" / "experimentalist-harbor-bridge")
    parser.add_argument("--token-env", default="NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN")
    parser.add_argument("--max-archive-bytes", type=int, default=DEFAULT_MAX_ARCHIVE_BYTES)
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"Harbor bridge token environment variable is not set: {args.token_env}")
    settings = HarborBridgeSettings(
        storage_root=args.storage_root,
        token=token,
        max_archive_bytes=args.max_archive_bytes,
    )
    uvicorn.run(create_app(settings=settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
