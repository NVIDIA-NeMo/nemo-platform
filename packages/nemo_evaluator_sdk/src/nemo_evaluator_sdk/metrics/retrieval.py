# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""BEIR-compatible corpus retrieval metrics."""

from __future__ import annotations

import math
from collections.abc import Callable

from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.metrics import (
    RetrievalMAP,
    RetrievalNDCG,
    RetrievalPrecision,
    RetrievalRecall,
)

__all__ = [
    "RetrievalMAPMetric",
    "RetrievalNDCGMetric",
    "RetrievalPrecisionMetric",
    "RetrievalRecallMetric",
]

_QRELS_FIELD = "qrels"
_SCORES_FIELD = "retrieval_scores"


class RetrievalNDCGMetric(RetrievalNDCG):
    """Mean query nDCG at configured cutoffs."""

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return per-query nDCG outputs."""
        return _output_spec("query_ndcg", self.k)

    def corpus_output_spec(self) -> list[MetricOutputSpec]:
        """Return mean corpus nDCG outputs."""
        return _output_spec("ndcg", self.k)

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute nDCG for one query."""
        qrels, ranked_ids = _extract_retrieval_input(input)
        return _outputs("query_ndcg", self.k, lambda cutoff: _ndcg(qrels, ranked_ids, cutoff))

    async def compute_corpus_scores(self, inputs: list[MetricInput]) -> MetricResult:
        """Compute mean nDCG across queries."""
        return await _mean_corpus_scores(self, inputs, row_name="query_ndcg", corpus_name="ndcg")


class RetrievalRecallMetric(RetrievalRecall):
    """Mean query recall at configured cutoffs."""

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return per-query recall outputs."""
        return _output_spec("query_recall", self.k)

    def corpus_output_spec(self) -> list[MetricOutputSpec]:
        """Return mean corpus recall outputs."""
        return _output_spec("recall", self.k)

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute recall for one query."""
        qrels, ranked_ids = _extract_retrieval_input(input)
        return _outputs("query_recall", self.k, lambda cutoff: _recall(qrels, ranked_ids, cutoff))

    async def compute_corpus_scores(self, inputs: list[MetricInput]) -> MetricResult:
        """Compute mean recall across queries."""
        return await _mean_corpus_scores(self, inputs, row_name="query_recall", corpus_name="recall")


class RetrievalPrecisionMetric(RetrievalPrecision):
    """Mean query precision at configured cutoffs."""

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return per-query precision outputs."""
        return _output_spec("query_precision", self.k)

    def corpus_output_spec(self) -> list[MetricOutputSpec]:
        """Return mean corpus precision outputs."""
        return _output_spec("precision", self.k)

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute precision for one query."""
        qrels, ranked_ids = _extract_retrieval_input(input)
        return _outputs("query_precision", self.k, lambda cutoff: _precision(qrels, ranked_ids, cutoff))

    async def compute_corpus_scores(self, inputs: list[MetricInput]) -> MetricResult:
        """Compute mean precision across queries."""
        return await _mean_corpus_scores(
            self,
            inputs,
            row_name="query_precision",
            corpus_name="precision",
        )


class RetrievalMAPMetric(RetrievalMAP):
    """Mean query average precision at configured cutoffs."""

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return per-query average precision outputs."""
        return _output_spec("query_map", self.k)

    def corpus_output_spec(self) -> list[MetricOutputSpec]:
        """Return corpus MAP outputs."""
        return _output_spec("map", self.k)

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute average precision for one query."""
        qrels, ranked_ids = _extract_retrieval_input(input)
        return _outputs("query_map", self.k, lambda cutoff: _average_precision(qrels, ranked_ids, cutoff))

    async def compute_corpus_scores(self, inputs: list[MetricInput]) -> MetricResult:
        """Compute MAP across queries."""
        return await _mean_corpus_scores(self, inputs, row_name="query_map", corpus_name="map")


def _output_spec(name: str, cutoffs: list[int]) -> list[MetricOutputSpec]:
    return [MetricOutputSpec.continuous_score(f"{name}@{cutoff}") for cutoff in cutoffs]


def _outputs(name: str, cutoffs: list[int], score: Callable[[int], float]) -> MetricResult:
    return MetricResult(outputs=[MetricOutput(name=f"{name}@{cutoff}", value=score(cutoff)) for cutoff in cutoffs])


def _extract_retrieval_input(input: MetricInput) -> tuple[dict[str, int], list[str]]:
    qrels_raw = input.row.data.get(_QRELS_FIELD)
    scores_raw = input.candidate.metadata.get(_SCORES_FIELD)
    if not isinstance(qrels_raw, dict) or not isinstance(scores_raw, dict):
        raise ValueError(
            f"retrieval metrics require row.data[{_QRELS_FIELD!r}] and candidate.metadata[{_SCORES_FIELD!r}] mappings"
        )
    try:
        qrels = {str(document_id): int(relevance) for document_id, relevance in qrels_raw.items()}
        scores = {str(document_id): float(score) for document_id, score in scores_raw.items()}
    except (TypeError, ValueError) as error:
        raise ValueError("retrieval qrels and scores must contain numeric values") from error
    ranked_ids = [document_id for document_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
    return qrels, ranked_ids


def _dcg(qrels: dict[str, int], ranked_ids: list[str], cutoff: int) -> float:
    # trec_eval's ndcg_cut uses graded relevance directly as gain.
    return sum(
        qrels.get(document_id, 0) / math.log2(rank + 1) for rank, document_id in enumerate(ranked_ids[:cutoff], start=1)
    )


def _ndcg(qrels: dict[str, int], ranked_ids: list[str], cutoff: int) -> float:
    ideal_relevances = sorted((relevance for relevance in qrels.values() if relevance > 0), reverse=True)
    ideal = sum(relevance / math.log2(rank + 1) for rank, relevance in enumerate(ideal_relevances[:cutoff], start=1))
    return _dcg(qrels, ranked_ids, cutoff) / ideal if ideal else 0.0


def _recall(qrels: dict[str, int], ranked_ids: list[str], cutoff: int) -> float:
    relevant = {document_id for document_id, relevance in qrels.items() if relevance > 0}
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked_ids[:cutoff])) / len(relevant)


def _precision(qrels: dict[str, int], ranked_ids: list[str], cutoff: int) -> float:
    relevant = {document_id for document_id, relevance in qrels.items() if relevance > 0}
    return len(relevant.intersection(ranked_ids[:cutoff])) / cutoff


def _average_precision(qrels: dict[str, int], ranked_ids: list[str], cutoff: int) -> float:
    relevant = {document_id for document_id, relevance in qrels.items() if relevance > 0}
    if not relevant:
        return 0.0
    relevant_seen = 0
    precision_sum = 0.0
    for rank, document_id in enumerate(ranked_ids[:cutoff], start=1):
        if document_id in relevant:
            relevant_seen += 1
            precision_sum += relevant_seen / rank
    return precision_sum / len(relevant)


async def _mean_corpus_scores(
    metric: RetrievalNDCGMetric | RetrievalRecallMetric | RetrievalPrecisionMetric | RetrievalMAPMetric,
    inputs: list[MetricInput],
    row_name: str,
    corpus_name: str,
) -> MetricResult:
    if not inputs:
        raise ValueError("retrieval corpus metrics require at least one query")
    per_query = [await metric.compute_scores(input) for input in inputs]
    return MetricResult(
        outputs=[
            MetricOutput(
                name=f"{corpus_name}@{cutoff}",
                value=sum(
                    next(output.value for output in result.outputs if output.name == f"{row_name}@{cutoff}")
                    for result in per_query
                )
                / len(per_query),
            )
            for cutoff in metric.k
        ]
    )
