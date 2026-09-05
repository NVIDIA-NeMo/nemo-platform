# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import math

import pytest
from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput
from nemo_evaluator_sdk.metrics.retrieval import (
    RetrievalMAPMetric,
    RetrievalNDCGMetric,
    RetrievalPrecisionMetric,
    RetrievalRecallMetric,
)
from nemo_evaluator_sdk.metrics.types import MetricsUnion
from pydantic import TypeAdapter


def _input(qrels: dict[str, int], scores: dict[str, float]) -> MetricInput:
    return MetricInput(
        row=DatasetRow(data={"qrels": qrels}),
        candidate=CandidateOutput(metadata={"retrieval_scores": scores}),
    )


@pytest.mark.asyncio
async def test_ndcg_matches_trec_eval_linear_gain() -> None:
    metric = RetrievalNDCGMetric(k=[1, 2])
    result = await metric.compute_scores(_input({"d1": 2, "d2": 1}, {"d2": 2.0, "d1": 1.0}))
    scores = {output.name: output.value for output in result.outputs}

    assert scores["query_ndcg@1"] == pytest.approx(0.5)
    expected = (1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3))
    assert scores["query_ndcg@2"] == pytest.approx(expected)


@pytest.mark.asyncio
async def test_recall_and_corpus_mean() -> None:
    metric = RetrievalRecallMetric(k=[1, 2])
    inputs = [
        _input({"d1": 1, "d2": 1}, {"d1": 2.0, "d3": 1.0}),
        _input({"d3": 1}, {"d3": 2.0, "d1": 1.0}),
    ]

    result = await metric.compute_corpus_scores(inputs)
    scores = {output.name: output.value for output in result.outputs}
    assert scores == {"recall@1": 0.75, "recall@2": 0.75}


@pytest.mark.asyncio
async def test_precision_and_map_match_trec_cutoff_semantics() -> None:
    input = _input(
        {"d1": 1, "d2": 1},
        {"d1": 3.0, "d3": 2.0, "d2": 1.0},
    )

    precision = await RetrievalPrecisionMetric(k=[2]).compute_scores(input)
    average_precision = await RetrievalMAPMetric(k=[3]).compute_scores(input)

    assert precision.outputs[0].value == pytest.approx(0.5)
    assert average_precision.outputs[0].value == pytest.approx((1.0 + 2 / 3) / 2)


def test_retrieval_metrics_are_registered_variants() -> None:
    adapter = TypeAdapter(MetricsUnion)

    metric = adapter.validate_python({"type": "retrieval-ndcg", "k": [10, 1]})

    assert isinstance(metric, RetrievalNDCGMetric)
    assert metric.k == [1, 10]


@pytest.mark.parametrize("k", [[], [0], [1, 1]])
def test_retrieval_metric_rejects_invalid_cutoffs(k: list[int]) -> None:
    with pytest.raises(ValueError):
        RetrievalRecallMetric(k=k)
