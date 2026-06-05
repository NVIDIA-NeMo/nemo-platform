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
- ``GET  /v1/health/live``  → ``{"object": "health-response", "message": "live"}``
  (200 whenever the process is up)
- ``GET  /v1/health/ready`` → ``{"object": "health-response", "message": "ready"}``
  (503 with ``"message": "not ready"`` until the model is loaded)

Runs inside the model container with no dependency on ``nemo_platform``; the
classifier is imported relative to this directory so the image can copy just
``model/`` plus its ``requirements.txt``.
"""

from __future__ import annotations

import logging
import os

import typer
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

try:  # package import (tests)
    from .classifier import JailbreakClassifier
except ImportError:  # flat import (container: `python server.py` from /app)
    from classifier import JailbreakClassifier

logger = logging.getLogger(__name__)

app = FastAPI(title="NeMo Jailbreak Detect", version="0.1.0")
cli_app = typer.Typer(help="NeMo jailbreak-detection model server.")

# Identifier reported by the OpenAI-style /v1/models discovery endpoint.
MODEL_ID = "nvidia/nemoguard-jailbreak-detect"

# Loaded once at startup and reused across requests.
_classifier: JailbreakClassifier | None = None


class ClassifyRequest(BaseModel):
    """Matches the NIM request shape.

    Bounds mirror the NIM's ``constr(min_length=1, max_length=16777216)``: reject
    empty input (the embedder would otherwise burn a forward pass on it) and
    absurdly large bodies at the API layer (the tokenizer truncates to 2048 tokens
    anyway). FastAPI returns 422 when these bounds are violated.
    """

    input: str = Field(min_length=1, max_length=16_777_216)


class ClassifyResponse(BaseModel):
    jailbreak: bool
    score: float


def get_classifier() -> JailbreakClassifier:
    """Return the process-global classifier, loading it on first use."""
    global _classifier
    if _classifier is None:
        _classifier = JailbreakClassifier(device=os.environ.get("JAILBREAK_CHECK_DEVICE"))
    return _classifier


@app.get("/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness: the process is up and serving HTTP, independent of model load."""
    return {"object": "health-response", "message": "live"}


@app.get("/v1/health/ready")
def health_ready(response: Response) -> dict[str, str]:
    """Readiness: only ready once the classifier is loaded.

    With ``--preload`` (default) the model loads before uvicorn binds, so this is
    ready immediately. With ``--no-preload`` it reports 503 until the first request
    triggers a lazy load, so an orchestrator's readiness probe reflects reality
    instead of routing traffic into a cold first request.
    """
    if _classifier is None:
        response.status_code = 503
        return {"object": "health-response", "message": "not ready"}
    return {"object": "health-response", "message": "ready"}


@app.get("/v1/models")
def list_models() -> dict:
    """OpenAI-style model discovery. Static — this server hosts a single model."""
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "owned_by": "nvidia"}],
    }


_MALFORMED_INPUT_DETAIL = (
    "Received malformed input. /v1/classify expects JSON with a single, string-valued field named `input`."
)


@app.post("/v1/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    try:
        classification, score = get_classifier()(request.input)
    except ValueError as exc:
        # Mirror the NIM: a malformed prompt that breaks tokenization/inference is
        # a client error (400), not a server fault (500).
        logger.info("%s Error details: %s", _MALFORMED_INPUT_DETAIL, exc)
        raise HTTPException(status_code=400, detail=_MALFORMED_INPUT_DETAIL) from exc
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
    # Surface our INFO startup logs (model download/load progress) on the console
    # before uvicorn configures its own logging.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if preload:
        # Surface model/download failures at boot instead of on first request,
        # so the controller's readiness probe reflects reality.
        logger.info("Preloading model before serving (this is the slow first-run step)...")
        get_classifier()
        logger.info("Model preloaded.")
    logger.info("Starting HTTP server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli_app()
