# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json

import httpx
import pytest
from nemo_evaluator_sdk.retrieval.nim_ranking import NimRankingClient
from nemo_evaluator_sdk.values.models import Model


@pytest.mark.asyncio
async def test_ranking_client_posts_v1_ranking_and_accepts_logits() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            content=json.dumps({"rankings": [{"index": 1, "logit": 0.2}, {"index": 0, "logit": 0.9}]}),
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ranked = await NimRankingClient(model=Model(url="https://rank.example.test/v1", name="rerank")).rank(
            "q",
            ["first", "second"],
            client=client,
        )

    assert ranked == [(1, 0.2), (0, 0.9)]
    assert requests[0].url == "https://rank.example.test/v1/ranking"
    assert json.loads(requests[0].content)["passages"] == [{"text": "first"}, {"text": "second"}]


@pytest.mark.asyncio
async def test_ranking_client_rewrites_reranking_and_embeddings_routes() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(
            200,
            request=request,
            content=json.dumps({"results": [{"index": 0, "score": 1.0}]}),
            headers={"content-type": "application/json"},
        )

    model = Model(url="https://igw.example.test/v1/embeddings", name="rerank")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await NimRankingClient(model=model).rank("q", ["only"], client=client)

    assert urls == ["https://igw.example.test/v1/ranking"]
