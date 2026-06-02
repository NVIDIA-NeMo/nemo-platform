# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for evaluator plugin adapters used by the standalone evaluator SDK."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator
from nemo_evaluator.sdk.standalone_sdk.backend import AsyncNMPBackend, NMPBackend
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.execution.backends.base import EvaluationBackend, SyncEvaluationBackend
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.values import RunConfig
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from pytest_mock import MockerFixture


class _SyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer sync-platform-token"}
        self.timeout = httpx.Timeout(42.0)
        self._client = MagicMock(spec=httpx.Client)


class _AsyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer platform-token"}
        self.timeout = httpx.Timeout(43.0)
        self._client = AsyncMock(spec=httpx.AsyncClient)


def _empty_evaluation_result() -> EvaluationResult:
    return EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))


def _empty_benchmark_result() -> BenchmarkEvaluationResult:
    return BenchmarkEvaluationResult(
        row_scores=[],
        aggregate_scores=AggregatedMetricResult(scores=[]),
        per_metric={},
    )


def _assert_sync_backend(backend: SyncEvaluationBackend) -> None:
    assert backend is not None


def _assert_async_backend(backend: EvaluationBackend) -> None:
    assert backend is not None


class TestNMPBackend:
    def test_satisfies_sync_standalone_sdk_backend_protocol(self) -> None:
        backend = NMPBackend(Evaluator(cast(NeMoPlatform, _SyncPlatform())))

        _assert_sync_backend(backend)

    def test_evaluate_local_delegates_to_resource_executor(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        expected = _empty_evaluation_result()
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", return_value=expected)
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote")
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(parallelism=2),
            dataset_glob_pattern="*.jsonl",
            prompt_template={"template": "{{item.input}}"},
            aggregate_fields=("mean",),
        )

        result = NMPBackend(resource).evaluate(metric=metric, request=request)

        assert result is expected
        local_evaluate.assert_called_once_with(
            metric=metric,
            dataset=request.dataset,
            params=request.params,
            target=request.target,
            dataset_glob_pattern=request.dataset_glob_pattern,
            field_mapping=request.field_mapping,
            prompt_template=request.prompt_template,
            aggregate_fields=request.aggregate_fields,
        )
        remote_evaluate.assert_not_called()

    def test_evaluate_remote_delegates_to_resource_executor_remote_path(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        expected = _empty_evaluation_result()
        local_evaluate = mocker.patch.object(resource._executor, "evaluate")
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote", return_value=expected)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])
        packager = CloudpickleMetricBundlePackager()

        result = NMPBackend(resource, execution_mode="remote", metric_bundle_packager=packager).evaluate(
            metric=metric, request=request
        )

        assert result is expected
        remote_evaluate.assert_called_once_with(
            metric=metric,
            request=request,
            metric_bundle_packager=packager,
        )
        local_evaluate.assert_not_called()

    def test_evaluate_remote_requires_metric_bundle_packager(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        local_evaluate = mocker.patch.object(resource._executor, "evaluate")
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote")
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])

        with pytest.raises(ValueError, match="metric_bundle_packager is required"):
            NMPBackend(resource, execution_mode="remote").evaluate(metric=metric, request=request)

        remote_evaluate.assert_not_called()
        local_evaluate.assert_not_called()

    def test_evaluate_benchmark_local_delegates_to_resource_executor(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        expected = _empty_benchmark_result()
        evaluate_benchmark = mocker.patch.object(resource._executor, "evaluate_benchmark", return_value=expected)
        metrics = [
            ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            StringCheckMetric(operation="contains", left_template="{{item.output}}", right_template="a"),
        ]
        request = EvaluationRequest(
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(parallelism=2),
            aggregate_fields=("mean",),
        )

        result = NMPBackend(resource).evaluate_benchmark(metrics=metrics, request=request)

        assert result is expected
        evaluate_benchmark.assert_called_once_with(
            metrics=metrics,
            request=request,
        )

    def test_evaluate_benchmark_remote_raises_without_local_run(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        evaluate_benchmark = mocker.patch.object(resource._executor, "evaluate_benchmark")
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])

        with pytest.raises(NotImplementedError, match="Remote evaluation of benchmarks"):
            NMPBackend(resource, execution_mode="remote").evaluate_benchmark(
                metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")],
                request=request,
            )

        evaluate_benchmark.assert_not_called()

    @pytest.mark.parametrize(
        "evaluation_request",
        [
            EvaluationRequest(dataset=[], preprocess_hooks=cast(Any, (object(),))),
            EvaluationRequest(dataset=[], postprocess_hooks=cast(Any, (object(),))),
        ],
    )
    def test_rejects_standalone_sdk_hooks(self, evaluation_request: EvaluationRequest) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))

        with pytest.raises(NotImplementedError, match="preprocess_hooks and postprocess_hooks"):
            NMPBackend(resource).evaluate(
                metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
                request=evaluation_request,
            )


class TestAsyncNMPBackend:
    def test_satisfies_async_standalone_sdk_backend_protocol(self) -> None:
        backend = AsyncNMPBackend(AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform())))

        _assert_async_backend(backend)

    @pytest.mark.asyncio
    async def test_evaluate_local_delegates_to_resource_executor(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        expected = _empty_evaluation_result()
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock(return_value=expected))
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote", new=AsyncMock())
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(parallelism=2),
            aggregate_fields=("mean",),
        )

        result = await AsyncNMPBackend(resource).evaluate(metric=metric, request=request)

        assert result is expected
        local_evaluate.assert_awaited_once_with(
            metric=metric,
            dataset=request.dataset,
            params=request.params,
            target=request.target,
            dataset_glob_pattern=request.dataset_glob_pattern,
            field_mapping=request.field_mapping,
            prompt_template=request.prompt_template,
            aggregate_fields=request.aggregate_fields,
        )
        remote_evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_remote_delegates_to_resource_executor_remote_path(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        expected = _empty_evaluation_result()
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock())
        remote_evaluate = mocker.patch.object(
            resource._executor, "evaluate_remote", new=AsyncMock(return_value=expected)
        )
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])
        packager = CloudpickleMetricBundlePackager()

        result = await AsyncNMPBackend(resource, execution_mode="remote", metric_bundle_packager=packager).evaluate(
            metric=metric, request=request
        )

        assert result is expected
        remote_evaluate.assert_awaited_once_with(
            metric=metric,
            request=request,
            metric_bundle_packager=packager,
        )
        local_evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_remote_requires_metric_bundle_packager(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock())
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote", new=AsyncMock())
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])

        with pytest.raises(ValueError, match="metric_bundle_packager is required"):
            await AsyncNMPBackend(resource, execution_mode="remote").evaluate(metric=metric, request=request)

        remote_evaluate.assert_not_awaited()
        local_evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_benchmark_local_delegates_to_resource_executor(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        expected = _empty_benchmark_result()
        evaluate_benchmark = mocker.patch.object(
            resource._executor,
            "evaluate_benchmark",
            new=AsyncMock(return_value=expected),
        )
        metrics: Sequence[Any] = [
            ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            StringCheckMetric(operation="contains", left_template="{{item.output}}", right_template="a"),
        ]
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])

        result = await AsyncNMPBackend(resource).evaluate_benchmark(metrics=metrics, request=request)

        assert result is expected
        evaluate_benchmark.assert_awaited_once_with(
            metrics=metrics,
            request=request,
        )

    @pytest.mark.asyncio
    async def test_evaluate_benchmark_remote_raises_without_local_run(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        evaluate_benchmark = mocker.patch.object(resource._executor, "evaluate_benchmark", new=AsyncMock())
        request = EvaluationRequest(dataset=[{"expected": "a", "output": "a"}])

        with pytest.raises(NotImplementedError, match="Remote evaluation of benchmarks"):
            await AsyncNMPBackend(resource, execution_mode="remote").evaluate_benchmark(
                metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")],
                request=request,
            )

        evaluate_benchmark.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_standalone_sdk_hooks(self) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        request = EvaluationRequest(dataset=[], preprocess_hooks=cast(Any, (object(),)))

        with pytest.raises(NotImplementedError, match="preprocess_hooks and postprocess_hooks"):
            await AsyncNMPBackend(resource).evaluate(
                metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
                request=request,
            )
