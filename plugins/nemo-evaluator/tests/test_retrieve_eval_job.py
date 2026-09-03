# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from nemo_evaluator.filesets import FilesetRef
from nemo_evaluator.jobs.retrieve_eval import (
    EVAL_RESULTS_FILE_NAME,
    EVAL_RESULTS_RESULT_NAME,
    RetrieveEvalInputSpec,
    RetrieveEvalJob,
    RetrieveEvalSpec,
)
from nemo_evaluator_sdk.retrieval.beir import BeirDataset
from nemo_evaluator_sdk.values.models import Model
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, AggregateRangeScore
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.jobs.api_factory import CPUExecutionProviderSpec
from pydantic import ValidationError
from pytest_mock import MockerFixture


def _context(tmp_path: Path) -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=tmp_path / "persistent")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace="default",
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


def _spec() -> RetrieveEvalSpec:
    return RetrieveEvalSpec(
        dataset=FilesetRef("default/retrieval-data"),
        target=Model(url="https://igw.example.test/v1/chat/completions", name="embed"),
        k=[1, 10],
    )


def _result(*, ndcg: float = 0.75, recall: float = 1.0) -> BenchmarkEvaluationResult:
    return BenchmarkEvaluationResult(
        row_scores=[],
        aggregate_scores=AggregatedMetricResult(
            scores=[
                AggregateRangeScore(
                    name="retrieval-ndcg.ndcg@10",
                    count=1,
                    nan_count=0,
                    mean=ndcg,
                ),
                AggregateRangeScore(
                    name="retrieval-recall.recall@10",
                    count=1,
                    nan_count=0,
                    mean=recall,
                ),
                AggregateRangeScore(
                    name="retrieval-precision.precision@10",
                    count=1,
                    nan_count=0,
                    mean=0.1,
                ),
                AggregateRangeScore(
                    name="retrieval-map.map@10",
                    count=1,
                    nan_count=0,
                    mean=0.7,
                ),
            ]
        ),
        per_metric={},
    )


@pytest.mark.parametrize("k", [[], [0], [1, 1]])
def test_input_spec_rejects_invalid_cutoffs(k: list[int]) -> None:
    with pytest.raises(ValidationError):
        RetrieveEvalInputSpec(dataset=FilesetRef("default/data"), target=_spec().target, k=k)


async def test_compile_builds_cpu_retrieve_eval_task() -> None:
    job = await RetrieveEvalJob.compile(
        workspace="default",
        spec=_spec(),
        entity_client=object(),
        job_name=None,
        async_sdk=None,
    )

    step = job.steps[0]
    assert step.name == "retrieve-eval"
    assert isinstance(step.executor, CPUExecutionProviderSpec)
    assert step.executor.container.command == ["nemo_evaluator.tasks.retrieve_eval"]


def test_run_validates_fileset_and_persists_nemotron_keys(tmp_path: Path, mocker: MockerFixture) -> None:
    ctx = _context(tmp_path)
    downloaded = tmp_path / "downloaded"
    download = mocker.patch(
        "nemo_evaluator.jobs.retrieve_eval.download_dataset_sync",
        return_value=downloaded,
    )
    dataset = mocker.Mock(spec=BeirDataset)
    load = mocker.patch("nemo_evaluator.jobs.retrieve_eval.load_beir_dataset", return_value=dataset)
    evaluator = mocker.Mock()
    evaluator.run_sync.return_value = _result()
    mocker.patch("nemo_evaluator.jobs.retrieve_eval.Evaluator", return_value=evaluator)
    sdk = SimpleNamespace()

    output = RetrieveEvalJob().run(_spec().model_dump(mode="json"), ctx=ctx, sdk=cast(NeMoPlatform, sdk))

    download.assert_called_once()
    load.assert_called_once_with(downloaded)
    assert evaluator.run_sync.call_args.kwargs["retrieval"] is dataset
    assert output["eval_results"] == {
        "ndcg@10": 0.75,
        "recall@10": 1.0,
        "precision@10": 0.1,
        "map@10": 0.7,
    }
    assert json.loads((ctx.storage.persistent / EVAL_RESULTS_FILE_NAME).read_text()) == output["eval_results"]
    assert (ctx.storage.persistent / "results" / EVAL_RESULTS_RESULT_NAME).exists()


def test_run_reports_relative_baseline_scores(tmp_path: Path, mocker: MockerFixture) -> None:
    ctx = _context(tmp_path)
    mocker.patch(
        "nemo_evaluator.jobs.retrieve_eval.download_dataset_sync",
        return_value=tmp_path / "downloaded",
    )
    mocker.patch(
        "nemo_evaluator.jobs.retrieve_eval.load_beir_dataset",
        return_value=mocker.Mock(spec=BeirDataset),
    )
    evaluator = mocker.Mock()
    evaluator.run_sync.side_effect = [
        _result(ndcg=0.75, recall=0.9),
        _result(ndcg=0.5, recall=0.75),
    ]
    mocker.patch("nemo_evaluator.jobs.retrieve_eval.Evaluator", return_value=evaluator)
    spec = _spec().model_copy(update={"baseline": Model(url="https://igw.example.test/v1", name="baseline")})

    output = RetrieveEvalJob().run(
        spec.model_dump(mode="json"),
        ctx=ctx,
        sdk=cast(NeMoPlatform, SimpleNamespace()),
    )

    assert evaluator.run_sync.call_count == 2
    assert output["relative"] == pytest.approx({"ndcg@10": 0.5, "recall@10": 0.2})
