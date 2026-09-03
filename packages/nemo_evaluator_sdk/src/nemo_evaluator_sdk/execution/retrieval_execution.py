# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dedicated corpus retrieval execution path."""

from __future__ import annotations

from collections.abc import Sequence

from nemo_evaluator_sdk.execution.scoring import finalize_evaluation_result, score_row
from nemo_evaluator_sdk.execution.utils import unique_metric_keys
from nemo_evaluator_sdk.metrics.protocol import CorpusMetric, Metric
from nemo_evaluator_sdk.retrieval.beir import BeirDataset
from nemo_evaluator_sdk.retrieval.dense_search import dense_search
from nemo_evaluator_sdk.retrieval.nim_embeddings import NimEmbeddingClient
from nemo_evaluator_sdk.values.models import Model
from nemo_evaluator_sdk.values.multi_metric_results import (
    BenchmarkEvaluationResult,
    collapse_results,
    namespace_result,
)

__all__ = ["evaluate_retrieval"]


async def evaluate_retrieval(
    retrieval: BeirDataset,
    target: Model,
    metrics: Sequence[Metric],
) -> BenchmarkEvaluationResult:
    """Run exact dense retrieval once and fan its rankings out to corpus metrics."""
    if not metrics:
        raise ValueError("retrieval evaluation requires at least one metric")
    unsupported = [
        metric.type
        for metric in metrics
        if not isinstance(metric, CorpusMetric)
        or not isinstance(getattr(metric, "k", None), list)
        or not getattr(metric, "k")
    ]
    if unsupported:
        raise TypeError(
            f"retrieval evaluation requires CorpusMetric implementations with retrieval cutoffs, got: {unsupported}"
        )

    max_k = max(
        (max(cutoffs) for metric in metrics if isinstance((cutoffs := getattr(metric, "k", None)), list) and cutoffs),
        default=None,
    )
    rankings = await dense_search(
        retrieval,
        NimEmbeddingClient(model=target),
        top_k=max_k,
    )
    items = [
        {
            "query_id": query_id,
            "query": retrieval.queries[query_id].text,
            "qrels": retrieval.qrels[query_id],
        }
        for query_id in retrieval.qrels
    ]
    samples = [{"retrieval_scores": rankings[query_id]} for query_id in retrieval.qrels]

    results_by_key = {}
    for metric_key, metric in zip(unique_metric_keys(metrics), metrics, strict=True):
        completed = [
            await score_row(
                metric,
                row,
                sample,
                index,
                metric_key,
                True,
                [],
            )
            for index, (row, sample) in enumerate(zip(items, samples, strict=True))
        ]
        result = await finalize_evaluation_result(metric, completed)
        results_by_key[metric_key] = namespace_result(metric_key, result, aggregate_fields=None)
    return collapse_results(results_by_key, aggregate_fields=None)
