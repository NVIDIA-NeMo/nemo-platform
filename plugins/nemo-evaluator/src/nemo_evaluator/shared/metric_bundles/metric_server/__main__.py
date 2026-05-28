# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tiny HTTP server runtime for container-bundled evaluator metrics."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol, cast

import cloudpickle

METRIC_ARTIFACT_NAME = "metric.pkl"
METRIC_DESCRIPTOR_NAME = "descriptor.json"

with open(METRIC_ARTIFACT_NAME, "rb") as f:
    metric = cloudpickle.load(f)

with open(METRIC_DESCRIPTOR_NAME) as f:
    metric_descriptor = json.load(f)


class ModelDumpable(Protocol):
    """Protocol for Pydantic-like result objects."""

    def model_dump(self, *, mode: str) -> object:
        """Return a JSON-compatible dump."""
        ...


@dataclass
class DatasetRow:
    """Duck-typed subset of SDK metric row input needed by bundled metrics."""

    row_index: int | None
    data: dict[str, Any]


@dataclass
class CandidateOutput:
    """Duck-typed subset of SDK candidate input needed by bundled metrics."""

    output_text: str | None = None
    response: Any | None = None
    trajectory: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_sample(self) -> dict[str, Any]:
        """Return a sample-shaped payload for template rendering helpers."""
        sample = dict(self.metadata)
        if self.output_text is not None:
            sample["output_text"] = self.output_text
        if self.response is not None:
            sample["response"] = self.response
        if self.trajectory is not None:
            sample["trajectory"] = self.trajectory
        return sample


@dataclass
class MetricInput:
    """Duck-typed metric input for container-local scoring."""

    row: DatasetRow
    candidate: CandidateOutput


def _metric_input_from_payload(payload: dict[str, Any]) -> MetricInput:
    row = payload.get("row")
    candidate = payload.get("candidate")
    if not isinstance(row, dict) or not isinstance(candidate, dict):
        raise ValueError("score payload must include row and candidate objects")
    data = row.get("data", {})
    metadata = candidate.get("metadata", {})
    if not isinstance(data, dict):
        raise ValueError("score payload row.data must be an object")
    if not isinstance(metadata, dict):
        raise ValueError("score payload candidate.metadata must be an object")
    row_index = row.get("row_index")
    if row_index is not None and not isinstance(row_index, int):
        raise ValueError("score payload row.row_index must be an integer or null")
    output_text = candidate.get("output_text")
    if output_text is not None and not isinstance(output_text, str):
        raise ValueError("score payload candidate.output_text must be a string or null")
    return MetricInput(
        row=DatasetRow(row_index=row_index, data=data),
        candidate=CandidateOutput(
            output_text=output_text,
            response=candidate.get("response"),
            trajectory=candidate.get("trajectory"),
            metadata=metadata,
        ),
    )


def _jsonable_result(result: object) -> object:
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        return cast(ModelDumpable, result).model_dump(mode="json")
    return result


async def _compute_scores(payload: dict[str, Any]) -> object:
    result = metric.compute_scores(_metric_input_from_payload(payload))
    if inspect.isawaitable(result):
        return await result
    return result


class MetricServerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for one bundled metric."""

    server_version = "NemoMetricServer/1.0"

    def do_GET(self) -> None:
        """Handle health and descriptor requests."""
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/descriptor":
            self._send_json(HTTPStatus.OK, metric_descriptor)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        """Handle scoring requests."""
        if self.path != "/score":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            payload = self._read_json_body()
            result = asyncio.run(_compute_scores(payload))
            self._send_json(HTTPStatus.OK, _jsonable_result(result))
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "traceback": traceback.format_exc()},
            )

    def log_message(self, format: str, *args: object) -> None:
        """Suppress per-request access logs by default."""
        del format, args

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Run the metric server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), MetricServerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
