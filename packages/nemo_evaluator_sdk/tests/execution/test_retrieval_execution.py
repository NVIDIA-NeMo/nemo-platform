# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.metrics.retrieval import RetrievalNDCGMetric, RetrievalRecallMetric
from nemo_evaluator_sdk.retrieval.beir import BeirCorpusDocument, BeirDataset, BeirQuery
from nemo_evaluator_sdk.values.models import Model


def _dataset(tmp_path: Path) -> BeirDataset:
    return BeirDataset(
        root=tmp_path,
        corpus={
            "d1": BeirCorpusDocument(id="d1", text="one"),
            "d2": BeirCorpusDocument(id="d2", text="two"),
        },
        queries={
            "q1": BeirQuery(id="q1", text="one?"),
            "q2": BeirQuery(id="q2", text="two?"),
        },
        qrels={"q1": {"d1": 1}, "q2": {"d2": 1}},
    )


async def _fake_dense_search(*args, **kwargs) -> dict[str, dict[str, float]]:
    return {
        "q1": {"d1": 1.0, "d2": 0.0},
        "q2": {"d1": 1.0, "d2": 0.0},
    }


@pytest.mark.asyncio
async def test_run_retrieval_shape_returns_query_rows_and_corpus_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "nemo_evaluator_sdk.execution.retrieval_execution.dense_search",
        _fake_dense_search,
    )

    result = await Evaluator().run(
        retrieval=_dataset(tmp_path),
        target=Model(url="https://embed.example.test/v1", name="embed"),
        metrics=[RetrievalNDCGMetric(k=[1]), RetrievalRecallMetric(k=[1])],
    )

    assert len(result.row_scores) == 2
    scores = {score.name: score.mean for score in result.aggregate_scores.scores}
    assert scores["retrieval-ndcg.ndcg@1"] == pytest.approx(0.5)
    assert scores["retrieval-recall.recall@1"] == pytest.approx(0.5)


def test_run_sync_supports_retrieval_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_evaluator_sdk.execution.retrieval_execution.dense_search",
        _fake_dense_search,
    )

    result = Evaluator().run_sync(
        retrieval=_dataset(tmp_path),
        target=Model(url="https://embed.example.test/v1", name="embed"),
        metrics=[RetrievalRecallMetric(k=[1])],
    )

    assert result.aggregate_scores.scores[-1].name == "retrieval-recall.recall@1"


@pytest.mark.asyncio
async def test_retrieval_and_dataset_are_mutually_exclusive(tmp_path: Path) -> None:
    run: Any = Evaluator().run
    with pytest.raises(ValueError, match="mutually exclusive"):
        await run(
            dataset=[],
            retrieval=_dataset(tmp_path),
            target=Model(url="https://embed.example.test/v1", name="embed"),
            metrics=[RetrievalRecallMetric(k=[1])],
        )
