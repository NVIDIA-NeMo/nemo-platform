# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NVIDIA NIM reranking client."""

from __future__ import annotations

import asyncio
import math
from urllib.parse import urlparse, urlunparse

import httpx
from nemo_evaluator_sdk.constants import PLACEHOLDER_INFERENCE_API_KEY
from nemo_evaluator_sdk.values.models import Model
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["NimRankingClient", "NimRankingError"]

_NVIDIA_HOSTED_INFERENCE_HOSTS = frozenset({"inference-api.nvidia.com", "integrate.api.nvidia.com"})


class NimRankingError(RuntimeError):
    """Raised when NIM returns an unusable ranking response."""


class NimRankingClient(BaseModel):
    """Rank query/passage pairs using a NIM ranking endpoint."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: Model
    max_retries: int = Field(default=3, ge=0)
    timeout: float = Field(default=60.0, gt=0)

    async def rank(
        self,
        query: str,
        passages: list[str],
        client: httpx.AsyncClient | None = None,
        truncate: str = "END",
    ) -> list[tuple[int, float]]:
        """Return ``(passage_index, logit)`` pairs in NIM ranking order."""
        if not passages:
            return []

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
        try:
            for attempt in range(self.max_retries + 1):
                hosted_contract = _uses_nvidia_hosted_contract(self.model)
                response = await client.post(
                    _rerank_url(self.model.url) if hosted_contract else _ranking_url(self.model.url),
                    headers=_headers(self.model),
                    json=(
                        {
                            "model": self.model.name,
                            "query": query,
                            "documents": passages,
                        }
                        if hosted_contract
                        else {
                            "model": self.model.name,
                            "query": {"text": query},
                            "passages": [{"text": passage} for passage in passages],
                            "truncate": truncate,
                        }
                    ),
                )
                response.raise_for_status()
                ranked = _parse_rankings(response, expected_count=len(passages))
                if all(math.isfinite(logit) for _, logit in ranked):
                    return ranked
                if attempt < self.max_retries:
                    await asyncio.sleep(min(0.1 * 2**attempt, 1.0))
        finally:
            if owns_client:
                await client.aclose()

        raise NimRankingError(f"ranking endpoint returned non-finite values after {self.max_retries + 1} attempts")


def _ranking_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/embeddings"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if path.endswith("/reranking"):
        path = f"{path[: -len('/reranking')]}/ranking"
    if not path.endswith("/ranking"):
        path = f"{path}/ranking"
    return urlunparse(parsed._replace(path=path))


def _rerank_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/embeddings", "/reranking", "/ranking"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/rerank"):
        path = f"{path}/rerank"
    return urlunparse(parsed._replace(path=path))


def _uses_nvidia_hosted_contract(model: Model) -> bool:
    endpoint = model.host_url or model.url
    return urlparse(endpoint).hostname in _NVIDIA_HOSTED_INFERENCE_HOSTS


def _headers(model: Model) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {model.api_key or PLACEHOLDER_INFERENCE_API_KEY}",
        "Content-Type": "application/json",
        **(model.default_headers or {}),
    }


def _parse_rankings(response: httpx.Response, expected_count: int) -> list[tuple[int, float]]:
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("ranking response must be an object")
        rankings = payload.get("rankings", payload.get("results"))
        if not isinstance(rankings, list):
            raise TypeError("ranking response must include a rankings list")
        parsed = [
            (int(item["index"]), float(item.get("logit", item.get("score", item.get("relevance_score")))))
            for item in rankings
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise NimRankingError("ranking endpoint returned an invalid response") from error
    if len(parsed) != expected_count:
        raise NimRankingError(f"expected {expected_count} rankings, received {len(parsed)}")
    return parsed
