# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-compatible NVIDIA NIM embedding client."""

from __future__ import annotations

import asyncio
import math
from typing import Literal
from urllib.parse import urlparse, urlunparse

import httpx
from nemo_evaluator_sdk.constants import PLACEHOLDER_INFERENCE_API_KEY
from nemo_evaluator_sdk.values.models import Model
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["NimEmbeddingClient", "NimEmbeddingError"]

InputType = Literal["query", "passage"]


class NimEmbeddingError(RuntimeError):
    """Raised when NIM returns unusable embeddings."""


class NimEmbeddingClient(BaseModel):
    """Encode query or passage batches using a NIM embedding endpoint."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: Model
    dimensions: int = Field(default=2048, gt=0)
    max_retries: int = Field(default=3, ge=0)
    timeout: float = Field(default=60.0, gt=0)

    async def encode(
        self,
        inputs: list[str],
        input_type: InputType,
        client: httpx.AsyncClient | None = None,
    ) -> list[list[float]]:
        """Encode ``inputs``, retrying responses containing non-finite values."""
        if not inputs:
            return []

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
        try:
            for attempt in range(self.max_retries + 1):
                response = await client.post(
                    _embeddings_url(self.model.url),
                    headers=_headers(self.model),
                    json={
                        "model": self.model.name,
                        "input": inputs,
                        "input_type": input_type,
                        "encoding_format": "float",
                    },
                )
                response.raise_for_status()
                embeddings = _parse_embeddings(response, expected_count=len(inputs), dimensions=self.dimensions)
                if all(math.isfinite(value) for embedding in embeddings for value in embedding):
                    return embeddings
                if attempt < self.max_retries:
                    await asyncio.sleep(min(0.1 * 2**attempt, 1.0))
        finally:
            if owns_client:
                await client.aclose()

        raise NimEmbeddingError(f"embedding endpoint returned non-finite values after {self.max_retries + 1} attempts")


def _embeddings_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/embeddings"):
        path = f"{path}/embeddings"
    return urlunparse(parsed._replace(path=path))


def _headers(model: Model) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {model.api_key or PLACEHOLDER_INFERENCE_API_KEY}",
        "Content-Type": "application/json",
        **(model.default_headers or {}),
    }


def _parse_embeddings(
    response: httpx.Response,
    expected_count: int,
    dimensions: int,
) -> list[list[float]]:
    try:
        data = response.json()["data"]
        ordered = sorted(data, key=lambda item: item["index"])
        embeddings = [item["embedding"] for item in ordered]
    except (KeyError, TypeError, ValueError) as error:
        raise NimEmbeddingError("embedding endpoint returned an invalid response") from error
    if len(embeddings) != expected_count:
        raise NimEmbeddingError(f"expected {expected_count} embeddings, received {len(embeddings)}")
    for embedding in embeddings:
        if not isinstance(embedding, list) or len(embedding) != dimensions:
            actual = len(embedding) if isinstance(embedding, list) else type(embedding).__name__
            raise NimEmbeddingError(f"expected embedding dimension {dimensions}, received {actual}")
        if not all(isinstance(value, int | float) and not isinstance(value, bool) for value in embedding):
            raise NimEmbeddingError("embedding values must be numbers")
    return embeddings
