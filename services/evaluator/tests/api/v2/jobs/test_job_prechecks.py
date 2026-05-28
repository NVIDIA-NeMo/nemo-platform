# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for job prechecks in MetricsManager and BenchmarksManager.

These tests verify that model prechecks are properly invoked during compile_job
for different job types.
"""

from unittest import mock

import nmp.evaluator.entities as entities
import pytest
from nemo_evaluator_sdk.values import (
    DatasetRows,
    JSONScoreParser,
    Model,
)
from nmp.evaluator.api.v2.benchmarks.manager import BenchmarksManager
from nmp.evaluator.api.v2.benchmarks.schemas.jobs import (
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
)
from nmp.evaluator.api.v2.metrics.manager import MetricsManager
from nmp.evaluator.api.v2.metrics.schemas.jobs import (
    MetricOfflineJob,
    MetricOnlineJob,
)
from nmp.evaluator.app.values import BenchmarkRef, FilesetRef, MetricRef
from nmp.evaluator.app.values.common import ModelRef
from pydantic import ValidationError


@pytest.fixture
def mock_entity_client():
    """Mock entity client for manager tests."""
    return mock.AsyncMock()


# mock_sdk fixture is now provided by conftest.py


@pytest.fixture
def mock_fileset_check():
    """Mock fileset existence check to always pass.

    Mocks the underlying fileset_exists function that all fileset checks use.
    """
    with mock.patch(
        "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists",
        new_callable=mock.AsyncMock,
    ) as fileset_mock:
        fileset_mock.return_value = True
        yield fileset_mock


class TestMetricJobPrechecks:
    """Tests for metric job prechecks."""

    def test_metric_online_job_accepts_optional_fields(self):
        job = MetricOnlineJob(
            metric=MetricRef(root="test/bleu"),
            model=Model(url="http://model.test/v1", name="test-model"),
            dataset=DatasetRows(rows=[{"input": "test"}]),
            prompt_template="{{input}}{{reference}}",
            optional_fields=["reference"],
        )

        assert job.optional_fields == ["reference"]

    def test_metric_online_job_rejects_empty_optional_field(self):
        with pytest.raises(ValidationError):
            MetricOnlineJob(
                metric=MetricRef(root="test/bleu"),
                model=Model(url="http://model.test/v1", name="test-model"),
                dataset=DatasetRows(rows=[{"input": "test"}]),
                prompt_template="{{input}}{{reference}}",
                optional_fields=[""],
            )

    @pytest.mark.asyncio
    async def test_offline_job_no_model_check(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """Offline job without model should not trigger model check."""
        # Use a metric reference and mock get_metric to return the entity
        metric_ref = MetricRef(root="test/bleu")
        metric_entity = entities.BLEUMetric(workspace="test", name="bleu", references=[])

        job = MetricOfflineJob(
            metric=metric_ref,
            dataset=DatasetRows(rows=[{"input": "test", "output": "test"}]),
        )

        manager = MetricsManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock) as mock_get_metric,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.app.jobs.metrics.compile_metric_job",
                new_callable=mock.AsyncMock,
            ) as mock_compile,
        ):
            mock_get_metric.return_value = metric_entity
            mock_compile.return_value = mock.MagicMock()

            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            # verify_model_reachable should NOT be called (no model in offline job)
            mock_verify.assert_not_called()

    @pytest.mark.asyncio
    async def test_online_job_model_check_called(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """Online job with model should trigger model check."""
        # Use a metric reference and mock get_metric to return the entity
        metric_ref = MetricRef(root="test/bleu")
        metric_entity = entities.BLEUMetric(workspace="test", name="bleu", references=[])

        job = MetricOnlineJob(
            metric=metric_ref,
            model=Model(url="http://model.test/v1", name="test-model"),
            dataset=DatasetRows(rows=[{"input": "test"}]),
            prompt_template="{{input}}",
        )

        manager = MetricsManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock) as mock_get_metric,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.app.jobs.metrics.compile_metric_job",
                new_callable=mock.AsyncMock,
            ) as mock_compile,
        ):
            mock_get_metric.return_value = metric_entity
            mock_verify.return_value = {"status": "ok"}
            mock_compile.return_value = mock.MagicMock()

            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            # verify_model_reachable should be called for the job model
            mock_verify.assert_called_once()
            call_args = mock_verify.call_args[0][0]
            # Handle both Model objects and dicts
            if isinstance(call_args, dict):
                assert call_args["url"] == "http://model.test/v1"
                assert call_args["name"] == "test-model"
            else:
                assert call_args.url == "http://model.test/v1"
                assert call_args.name == "test-model"

    @pytest.mark.asyncio
    async def test_online_job_model_ref_resolved_before_model_check(
        self, mock_entity_client, mock_sdk, mock_fileset_check
    ):
        """Online job ModelRef should be resolved to Model before prechecks."""
        metric_ref = "test/bleu"
        metric_entity = entities.BLEUMetric(workspace="test", name="bleu", references=[])
        resolved_model = Model(url="http://resolved-model.test/v1", name="resolved-model")

        job = MetricOnlineJob.model_validate(
            {
                "metric": metric_ref,
                "model": "test-workspace/resolved-model",
                "dataset": {"rows": [{"input": "test"}]},
                "prompt_template": "{{input}}",
            }
        )

        manager = MetricsManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock) as mock_get_metric,
            mock.patch(
                "nmp.evaluator.api.v2.metrics.manager.resolve_model",
                new_callable=mock.AsyncMock,
                return_value=resolved_model,
            ) as mock_resolve_model,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.app.jobs.metrics.compile_metric_job",
                new_callable=mock.AsyncMock,
            ) as mock_compile,
        ):
            mock_get_metric.return_value = metric_entity
            mock_verify.return_value = {"status": "ok"}
            mock_compile.return_value = mock.MagicMock()

            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            mock_resolve_model.assert_called_once()
            assert isinstance(mock_resolve_model.call_args[0][0], ModelRef)
            mock_verify.assert_called_once()
            call_args = mock_verify.call_args[0][0]
            if isinstance(call_args, dict):
                assert call_args["url"] == "http://resolved-model.test/v1"
                assert call_args["name"] == "resolved-model"
            else:
                assert call_args.url == "http://resolved-model.test/v1"
                assert call_args.name == "resolved-model"

    @pytest.mark.asyncio
    async def test_online_job_rewrites_model_url_only_for_compiled_payload(
        self, mock_entity_client, mock_sdk, mock_fileset_check
    ):
        """Prechecks use the original model URL, but compiled jobs get the rewritten URL."""
        metric_entity = entities.BLEUMetric(workspace="test", name="bleu", references=[])
        job = MetricOnlineJob(
            metric=MetricRef(root="test/bleu"),
            model=Model(
                url="http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1",
                name="demo",
            ),
            dataset=DatasetRows(rows=[{"input": "test"}]),
            prompt_template="{{input}}",
        )
        manager = MetricsManager(mock_entity_client)

        def rewrite_payload(payload: dict) -> dict:
            rewritten = dict(payload)
            rewritten["model"] = dict(payload["model"])
            rewritten["model"]["url"] = (
                "http://container-host:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
            )
            return rewritten

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock, return_value=metric_entity),
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
                return_value={"status": "ok"},
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.api.v2.metrics.manager.rewrite_models_for_job_container",
                side_effect=rewrite_payload,
            ),
            mock.patch(
                "nmp.evaluator.api.v2.metrics.manager.compile_metric_job",
                new_callable=mock.AsyncMock,
                return_value=mock.MagicMock(),
            ) as mock_compile,
        ):
            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            checked_model = mock_verify.call_args[0][0]
            if isinstance(checked_model, dict):
                assert checked_model["url"] == (
                    "http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
                )
            else:
                assert checked_model.url == (
                    "http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
                )

            compiled_job = mock_compile.call_args[0][0]
            assert compiled_job.model.url == (
                "http://container-host:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
            )

    @pytest.mark.asyncio
    async def test_model_check_failure_raises_error(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """Model check failure should raise ValueError."""
        # Use a metric reference and mock get_metric to return the entity
        metric_ref = MetricRef(root="test/bleu")
        metric_entity = entities.BLEUMetric(workspace="test", name="bleu", references=[])

        job = MetricOnlineJob(
            metric=metric_ref,
            model=Model(url="http://unreachable.test/v1", name="unreachable-model"),
            dataset=DatasetRows(rows=[{"input": "test"}]),
            prompt_template="{{input}}",
        )

        manager = MetricsManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock) as mock_get_metric,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
        ):
            mock_get_metric.return_value = metric_entity
            mock_verify.side_effect = Exception("Connection refused")

            with pytest.raises(ValueError, match="Job cannot be launched"):
                await manager.compile_job("test-workspace", job, sdk=mock_sdk)

    @pytest.mark.asyncio
    async def test_llm_judge_failed_model_raises_error(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """LLM Judge metric with unreachable job.metric.model should raise ValueError."""
        from nemo_evaluator_sdk.values.scores import RangeScore
        from nmp.evaluator.api.v2.metrics.schemas.metrics import LLMJudgeMetric

        # Create inline LLM Judge metric with unreachable model
        inline_metric = LLMJudgeMetric(
            model=Model(url="http://unreachable-judge.test/v1", name="unreachable-judge-model"),
            scores=[
                RangeScore(
                    name="quality",
                    description="Quality score",
                    minimum=1,
                    maximum=5,
                    parser=JSONScoreParser(json_path="score"),
                )
            ],
            prompt_template={"messages": [{"role": "user", "content": "Evaluate: {{item.response}}"}]},
        )

        job = MetricOfflineJob(
            metric=inline_metric,
            dataset=DatasetRows(rows=[{"response": "test response"}]),
        )

        manager = MetricsManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_metric", new_callable=mock.AsyncMock) as mock_get_metric,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
        ):
            # get_metric should return the validated inline metric
            mock_get_metric.return_value = inline_metric
            mock_verify.side_effect = Exception("Connection refused")

            with pytest.raises(ValueError, match="Job cannot be launched"):
                await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            # Should check the model from job.metric.model
            mock_verify.assert_called_once()
            call_args = mock_verify.call_args[0][0]
            # Handle both Model objects and dicts
            if isinstance(call_args, dict):
                assert call_args["url"] == "http://unreachable-judge.test/v1"
                assert call_args["name"] == "unreachable-judge-model"
            else:
                assert call_args.url == "http://unreachable-judge.test/v1"
                assert call_args.name == "unreachable-judge-model"


class TestBenchmarkJobPrechecks:
    """Tests for benchmark job prechecks."""

    def test_benchmark_online_job_accepts_optional_fields(self):
        job = BenchmarkOnlineJob(
            benchmark=BenchmarkRef(root="test/test-benchmark"),
            model=Model(url="http://model.test/v1", name="test-model"),
            prompt_template="{{input}}{{reference}}",
            optional_fields=["reference"],
        )

        assert job.optional_fields == ["reference"]

    def test_benchmark_online_job_rejects_empty_optional_field(self):
        with pytest.raises(ValidationError):
            BenchmarkOnlineJob(
                benchmark=BenchmarkRef(root="test/test-benchmark"),
                model=Model(url="http://model.test/v1", name="test-model"),
                prompt_template="{{input}}{{reference}}",
                optional_fields=[""],
            )

    def test_benchmark_online_agent_job_accepts_optional_fields(self):
        job = BenchmarkOnlineAgentJob(
            benchmark=BenchmarkRef(root="test/test-benchmark"),
            agent={"url": "http://agent.test/v1", "name": "test-agent", "format": "nemo_agent_toolkit"},
            prompt_template="{{input}}{{reference}}",
            optional_fields=["reference"],
        )

        assert job.optional_fields == ["reference"]

    def test_benchmark_online_agent_job_rejects_empty_optional_field(self):
        with pytest.raises(ValidationError):
            BenchmarkOnlineAgentJob(
                benchmark=BenchmarkRef(root="test/test-benchmark"),
                agent={"url": "http://agent.test/v1", "name": "test-agent", "format": "nemo_agent_toolkit"},
                prompt_template="{{input}}{{reference}}",
                optional_fields=[""],
            )

    @pytest.mark.asyncio
    async def test_online_benchmark_model_check_called(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """Online benchmark job with model should trigger model check."""
        # Create a minimal benchmark entity
        benchmark = entities.Benchmark(
            workspace="test",
            name="test-benchmark",
            description="Test benchmark",
            dataset=FilesetRef(root="test-workspace/test-dataset"),
            metrics=[entities.BLEUMetric(workspace="test", name="bleu", references=[])],
        )

        job = BenchmarkOnlineJob(
            benchmark=BenchmarkRef(root="test/test-benchmark"),
            model=Model(url="http://model.test/v1", name="test-model"),
            prompt_template="{{input}}",
        )

        manager = BenchmarksManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_benchmark", new_callable=mock.AsyncMock) as mock_get_benchmark,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.api.v2.benchmarks.manager.app.BenchmarkJobAdapter.validate_python",
            ) as mock_adapter,
            mock.patch(
                # Mock at manager import location to ensure it's the right function
                "nmp.evaluator.api.v2.benchmarks.manager.compile_benchmark_job",
                new_callable=mock.AsyncMock,
            ) as mock_compile,
        ):
            mock_get_benchmark.return_value = benchmark
            mock_verify.return_value = {"status": "ok"}
            mock_adapter.return_value = mock.MagicMock()
            mock_compile.return_value = mock.MagicMock()

            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            # verify_model_reachable should be called for the job model
            mock_verify.assert_called_once()
            call_args = mock_verify.call_args[0][0]
            # Handle both Model objects and dicts
            if isinstance(call_args, dict):
                assert call_args["url"] == "http://model.test/v1"
                assert call_args["name"] == "test-model"
            else:
                assert call_args.url == "http://model.test/v1"
                assert call_args.name == "test-model"

    @pytest.mark.asyncio
    async def test_online_benchmark_rewrites_model_url_only_for_compiled_payload(
        self, mock_entity_client, mock_sdk, mock_fileset_check
    ):
        """Benchmark prechecks use the original model URL, but compiled jobs get the rewritten URL."""
        benchmark = entities.Benchmark(
            workspace="test",
            name="test-benchmark",
            description="Test benchmark",
            dataset=FilesetRef(root="test-workspace/test-dataset"),
            metrics=[entities.BLEUMetric(workspace="test", name="bleu", references=[])],
        )
        job = BenchmarkOnlineJob(
            benchmark=BenchmarkRef(root="test/test-benchmark"),
            model=Model(
                url="http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1",
                name="demo",
            ),
            prompt_template="{{input}}",
        )
        manager = BenchmarksManager(mock_entity_client)

        def rewrite_payload(payload: dict) -> dict:
            rewritten = dict(payload)
            rewritten["model"] = dict(payload["model"])
            rewritten["model"]["url"] = (
                "http://container-host:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
            )
            return rewritten

        with (
            mock.patch.object(manager, "get_benchmark", new_callable=mock.AsyncMock, return_value=benchmark),
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
                return_value={"status": "ok"},
            ) as mock_verify,
            mock.patch(
                "nmp.evaluator.api.v2.benchmarks.manager.rewrite_models_for_job_container",
                side_effect=rewrite_payload,
            ),
            mock.patch(
                "nmp.evaluator.api.v2.benchmarks.manager.compile_benchmark_job",
                new_callable=mock.AsyncMock,
                return_value=mock.MagicMock(),
            ) as mock_compile,
        ):
            await manager.compile_job("test-workspace", job, sdk=mock_sdk)

            checked_model = mock_verify.call_args[0][0]
            if isinstance(checked_model, dict):
                assert checked_model["url"] == (
                    "http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
                )
            else:
                assert checked_model.url == (
                    "http://localhost:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
                )

            compiled_job = mock_compile.call_args[0][0]
            assert compiled_job.model.url == (
                "http://container-host:8080/apis/inference-gateway/v2/workspaces/test/model/demo/-/v1"
            )

    @pytest.mark.asyncio
    async def test_benchmark_model_check_failure_raises_error(self, mock_entity_client, mock_sdk, mock_fileset_check):
        """Model check failure should raise ValueError for benchmark jobs."""
        benchmark = entities.Benchmark(
            workspace="test",
            name="test-benchmark",
            description="Test benchmark",
            dataset=FilesetRef(root="test-workspace/test-dataset"),
            metrics=[entities.BLEUMetric(workspace="test", name="bleu", references=[])],
        )

        job = BenchmarkOnlineJob(
            benchmark=BenchmarkRef(root="test/test-benchmark"),
            model=Model(url="http://unreachable.test/v1", name="unreachable-model"),
            prompt_template="{{input}}",
        )

        manager = BenchmarksManager(mock_entity_client)

        with (
            mock.patch.object(manager, "get_benchmark", new_callable=mock.AsyncMock) as mock_get_benchmark,
            mock.patch(
                "nmp.evaluator.app.inference.verify_model_reachable",
                new_callable=mock.AsyncMock,
            ) as mock_verify,
        ):
            mock_get_benchmark.return_value = benchmark
            mock_verify.side_effect = Exception("Connection refused")

            with pytest.raises(ValueError, match="Job cannot be launched"):
                await manager.compile_job("test-workspace", job, sdk=mock_sdk)
