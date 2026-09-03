# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exact dense retrieval for small evaluation corpora."""

from __future__ import annotations

import math

import httpx
from nemo_evaluator_sdk.retrieval.beir import BeirDataset
from nemo_evaluator_sdk.retrieval.nim_embeddings import InputType, NimEmbeddingClient

__all__ = ["dense_search"]


async def dense_search(
    dataset: BeirDataset,
    embeddings: NimEmbeddingClient,
    batch_size: int = 32,
    top_k: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, dict[str, float]]:
    """Score every query against the corpus with cosine similarity."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be at least 1")

    document_ids = list(dataset.corpus)
    query_ids = list(dataset.queries)
    document_vectors = await _encode_batches(
        embeddings,
        [dataset.corpus[document_id].content for document_id in document_ids],
        input_type="passage",
        batch_size=batch_size,
        client=client,
    )
    query_vectors = await _encode_batches(
        embeddings,
        [dataset.queries[query_id].text for query_id in query_ids],
        input_type="query",
        batch_size=batch_size,
        client=client,
    )

    normalized_documents = [_normalize(vector) for vector in document_vectors]
    results: dict[str, dict[str, float]] = {}
    for query_id, query_vector in zip(query_ids, query_vectors, strict=True):
        normalized_query = _normalize(query_vector)
        ranked = sorted(
            (
                (document_id, sum(left * right for left, right in zip(normalized_query, document_vector, strict=True)))
                for document_id, document_vector in zip(document_ids, normalized_documents, strict=True)
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if top_k is not None:
            ranked = ranked[:top_k]
        results[query_id] = dict(ranked)
    return results


async def _encode_batches(
    embeddings: NimEmbeddingClient,
    texts: list[str],
    input_type: InputType,
    batch_size: int,
    client: httpx.AsyncClient | None,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(
            await embeddings.encode(
                texts[start : start + batch_size],
                input_type=input_type,
                client=client,
            )
        )
    return vectors


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("cannot search with a zero-length embedding")
    return [value / norm for value in vector]
