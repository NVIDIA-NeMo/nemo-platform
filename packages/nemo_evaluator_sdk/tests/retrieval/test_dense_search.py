# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import math
from pathlib import Path

import httpx
import pytest
from nemo_evaluator_sdk.retrieval.beir import BeirDataset
from nemo_evaluator_sdk.retrieval.dense_search import dense_search
from nemo_evaluator_sdk.retrieval.nim_embeddings import NimEmbeddingClient, NimEmbeddingError
from nemo_evaluator_sdk.values.models import Model


def _model() -> Model:
    return Model(url="https://embed.example.test/v1", name="embed-model")


def _response(request: httpx.Request, vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        content=json.dumps(
            {"data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)]},
            allow_nan=True,
        ),
        headers={"content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_embedding_client_sends_nim_input_type_and_checks_dimension() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(request, [[1.0, 0.0]])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vectors = await NimEmbeddingClient(model=_model(), dimensions=2).encode(
            ["question"],
            input_type="query",
            client=client,
        )

    assert vectors == [[1.0, 0.0]]
    assert requests[0].url == "https://embed.example.test/v1/embeddings"
    assert json.loads(requests[0].content) == {
        "model": "embed-model",
        "input": ["question"],
        "input_type": "query",
        "encoding_format": "float",
    }


@pytest.mark.asyncio
async def test_embedding_client_replaces_chat_completion_route() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(request, [[1.0, 0.0]])

    model = Model(
        url="https://igw.example.test/v1/chat/completions?model=embed",
        name="embed-model",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await NimEmbeddingClient(model=model, dimensions=2).encode(
            ["question"],
            input_type="query",
            client=client,
        )

    assert requests[0].url == "https://igw.example.test/v1/embeddings?model=embed"


@pytest.mark.asyncio
async def test_embedding_client_retries_non_finite_response() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        vector = [math.nan, 0.0] if attempts == 1 else [1.0, 0.0]
        return _response(request, [vector])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await NimEmbeddingClient(model=_model(), dimensions=2, max_retries=1).encode(
            ["question"],
            input_type="query",
            client=client,
        )

    assert attempts == 2
    assert result == [[1.0, 0.0]]


@pytest.mark.asyncio
async def test_embedding_client_rejects_wrong_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, [[1.0]])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NimEmbeddingError, match="expected embedding dimension 2"):
            await NimEmbeddingClient(model=_model(), dimensions=2).encode(
                ["question"],
                input_type="query",
                client=client,
            )


@pytest.mark.asyncio
async def test_dense_search_ranks_documents_and_uses_passage_then_query(tmp_path: Path) -> None:
    (tmp_path / "qrels").mkdir()
    (tmp_path / "corpus.jsonl").write_text(
        '{"_id":"d1","text":"alpha"}\n{"_id":"d2","text":"beta"}\n',
        encoding="utf-8",
    )
    (tmp_path / "queries.jsonl").write_text('{"_id":"q1","text":"alpha?"}\n', encoding="utf-8")
    (tmp_path / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\td1\t1\n",
        encoding="utf-8",
    )
    input_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        input_types.append(payload["input_type"])
        vectors = [[1.0, 0.0], [0.0, 1.0]] if payload["input_type"] == "passage" else [[0.8, 0.2]]
        return _response(request, vectors)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await dense_search(
            BeirDataset.from_path(tmp_path),
            NimEmbeddingClient(model=_model(), dimensions=2),
            client=client,
        )

    assert input_types == ["passage", "query"]
    assert list(results["q1"]) == ["d1", "d2"]
    assert results["q1"]["d1"] > results["q1"]["d2"]
