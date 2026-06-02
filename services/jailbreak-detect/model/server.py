# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone jailbreak-detection model server (NIM-compatible).

This is the deployable unit the platform controller manages. It exposes the
same HTTP contract as the NVIDIA NemoGuard JailbreakDetect NIM, so the
``nemoguardrails`` library needs **zero changes** — point
``rails.config.jailbreak_detection.nim_base_url`` at this server and set
``nim_server_endpoint`` to ``/v1/classify``.

Contract:

- ``POST /v1/classify``  body ``{"input": "<prompt>"}``  →
  ``{"jailbreak": <bool>, "score": <float>}``
- ``GET  /v1/health/ready`` → ``{"object": "health-response", "message": "ready"}``

Runs inside the model container with no dependency on ``nemo_platform``; the
classifier is imported relative to this directory so the image can copy just
``model/`` plus its ``requirements.txt``.
"""

from __future__ import annotations

import logging
import os

import typer
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

try:  # package import (tests)
    from .classifier import JailbreakClassifier
except ImportError:  # flat import (container: `python server.py` from /app)
    from classifier import JailbreakClassifier  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

app = FastAPI(title="NeMo Jailbreak Detect", version="0.1.0")
cli_app = typer.Typer(help="NeMo jailbreak-detection model server.")

# Identifier reported by the OpenAI-style /v1/models discovery endpoint.
MODEL_ID = "nvidia/nemoguard-jailbreak-detect"

# Loaded once at startup and reused across requests.
_classifier: JailbreakClassifier | None = None


class ClassifyRequest(BaseModel):
    """Matches the NIM request shape."""

    input: str


class ClassifyResponse(BaseModel):
    jailbreak: bool
    score: float


def get_classifier() -> JailbreakClassifier:
    """Return the process-global classifier, loading it on first use."""
    global _classifier
    if _classifier is None:
        _classifier = JailbreakClassifier(device=os.environ.get("JAILBREAK_CHECK_DEVICE"))
    return _classifier


@app.get("/v1/health/ready")
def health_ready() -> dict[str, str]:
    return {"object": "health-response", "message": "ready"}


@app.get("/v1/models")
def list_models() -> dict:
    """OpenAI-style model discovery. Static — this server hosts a single model."""
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "owned_by": "nvidia"}],
    }


@app.post("/v1/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    classification, score = get_classifier()(request.input)
    return ClassifyResponse(jailbreak=classification, score=score)


@cli_app.callback()
def _main() -> None:
    """NeMo jailbreak-detection model server."""
    # Present so Typer keeps `start` as an explicit subcommand (a single-command
    # Typer app otherwise collapses and rejects the command name).


@cli_app.command()
def start(
    port: int = typer.Option(default=8000, help="Port to listen on."),
    host: str = typer.Option(default="0.0.0.0", help="Host/IP to bind."),
    preload: bool = typer.Option(default=True, help="Load the model before serving."),
) -> None:
    """Start the model server."""
    if preload:
        # Surface model/download failures at boot instead of on first request,
        # so the controller's readiness probe reflects reality.
        get_classifier()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli_app()
