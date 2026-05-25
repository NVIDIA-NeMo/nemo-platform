# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the evaluator plugin's SDK-backed job."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from nemo_evaluator.cli import EvaluatorPluginCLI
from nemo_evaluator.jobs.evaluate import (
    AGGREGATE_SCORES_RESULT_NAME,
    ARTIFACTS_RESULT_NAME,
    DEFAULT_FILE_NAME,
    DEFAULT_RESULT_NAME,
    ROW_SCORES_RESULT_NAME,
    EvaluateJob,
    EvaluateSpec,
)
from nemo_evaluator.tasks.evaluate import main as evaluate_task_main
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.metrics.base import MetricBundle
from nemo_evaluator_sdk.metrics.cloudpickle import CloudpickleMetricBundler
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.values import (
    Agent,
    AggregatedMetricResult,
    EvaluationResult,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SecretRef,
)
from nemo_evaluator_sdk.values.scores import JSONScoreParser, RangeScore
from nemo_platform.types.jobs.platform_job_spec import PlatformJobSpec
from nemo_platform_plugin.commands import add_job_commands
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.scheduler import NemoJobScheduler
from nmp.evaluator.app.values import FilesetRef
from pydantic import BaseModel
from pytest_mock import MockerFixture
from typer.testing import CliRunner


def _exact_match_spec() -> dict:
    return {
        "metric": _bundle_payload(ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")),
        "dataset": [
            {"expected": "blue", "model_output": "Blue"},
            {"expected": "Jupiter", "model_output": "Saturn"},
        ],
        "params": {"parallelism": 2},
    }


def _bundle_payload(metric) -> dict[str, Any]:
    return CloudpickleMetricBundler().bundle(metric).model_dump(mode="json")


def _assert_metric_step_entrypoint(job_spec: PlatformJobSpec) -> None:
    step = job_spec.steps[0]
    container = cast(Any, step.executor).container
    assert container.entrypoint == ["python", "-m"]
    assert container.command == ["nemo_evaluator.tasks.evaluate"]


def _load_cli_run_payload(output: str) -> dict[str, Any]:
    """Return the evaluator run JSON payload from CLI stdout."""
    return cast(dict[str, Any], json.loads(output[output.index('{\n  "status"') :]))


def _make_job_context(tmp_path: Path) -> JobContext:
    """Return a local job context with persistent result storage."""
    storage = StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=tmp_path / "persistent")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace="dev",
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


def _empty_evaluation_result() -> EvaluationResult:
    """Return an SDK result object suitable for runner delegation tests."""
    return EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))


def _assert_saved_result_artifact(
    run_result: dict[str, Any], ctx: JobContext, result_payload: dict[str, object]
) -> None:
    """Assert that the evaluator result was persisted and registered."""
    assert run_result["artifact"] == {
        "name": DEFAULT_RESULT_NAME,
        "artifact_url": f"file://{ctx.storage.persistent / 'results' / DEFAULT_RESULT_NAME}",
    }
    result_path = ctx.storage.persistent / DEFAULT_FILE_NAME
    assert json.loads(result_path.read_text(encoding="utf-8")) == result_payload
    artifact_path = Path(run_result["artifact"]["artifact_url"].removeprefix("file://"))
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == result_payload
    assert (ctx.storage.persistent / "results" / AGGREGATE_SCORES_RESULT_NAME).exists()
    assert (ctx.storage.persistent / "results" / ROW_SCORES_RESULT_NAME).exists()
    assert (ctx.storage.persistent / "results" / ARTIFACTS_RESULT_NAME).is_dir()


def _load_artifact_payload(run_result: dict[str, Any]) -> dict[str, Any]:
    """Load a local artifact payload from a scheduler or CLI run result."""
    artifact_path = Path(run_result["artifact"]["artifact_url"].removeprefix("file://"))
    return cast(dict[str, Any], json.loads(artifact_path.read_text(encoding="utf-8")))


def test_evaluate_job_runs_inline_exact_match_metric() -> None:
    result = NemoJobScheduler().run_local(EvaluateJob, _exact_match_spec())

    assert result["status"] == "completed"
    assert "result" not in result
    aggregate_scores = _load_artifact_payload(result)["aggregate_scores"]["scores"]
    assert aggregate_scores[0]["name"] == "exact-match.exact-match"
    assert aggregate_scores[0]["mean"] == 0.5


def test_cli_explain_uses_registered_evaluator_job_key() -> None:
    app = EvaluatorPluginCLI().get_cli()
    add_job_commands(app, {"evaluator.evaluate": EvaluateJob})

    result = CliRunner().invoke(app, ["evaluate", "explain"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["job_key"] == "evaluator.evaluate"
    assert payload["endpoint"] == "/apis/evaluator/v2/workspaces/{workspace}/evaluate/jobs"
    assert payload["spec_schema"]["title"] == "EvaluateSpec"


def test_cli_info_reports_registered_evaluator_job_key() -> None:
    app = EvaluatorPluginCLI().get_cli()
    add_job_commands(app, {"evaluator.evaluate": EvaluateJob})

    result = CliRunner().invoke(app, ["info"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["jobs"] == ["evaluator.evaluate"]


def test_cli_run_executes_evaluator_job() -> None:
    app = EvaluatorPluginCLI().get_cli()
    add_job_commands(app, {"evaluator.evaluate": EvaluateJob})

    result = CliRunner().invoke(app, ["evaluate", "run", "--spec", json.dumps(_exact_match_spec())])

    assert result.exit_code == 0
    payload = _load_cli_run_payload(result.output)
    assert payload["status"] == "completed"
    assert "result" not in payload
    assert _load_artifact_payload(payload)["aggregate_scores"]["scores"][0]["mean"] == 0.5


async def test_evaluate_job_compile_produces_cpu_task_step() -> None:
    spec = EvaluateSpec.model_validate(_exact_match_spec())
    compiled = await EvaluateJob.compile(
        workspace="default",
        spec=spec,
        entity_client=object(),
        job_name=None,
        async_sdk=object(),
    )
    job_spec = PlatformJobSpec.model_validate(compiled)
    assert len(job_spec.steps) == 1
    step = job_spec.steps[0]
    assert step.name == "evaluate"
    _assert_metric_step_entrypoint(job_spec)
    assert step.config is not None
    config = cast(dict[str, Any], step.config)
    assert config["metric"]["bundle_kind"] == "metric-bundle"
    assert config["metric"]["metric_type"] == "exact-match"
    assert config["dataset"] == _exact_match_spec()["dataset"]


async def test_evaluate_job_compile_produces_online_model_job() -> None:
    spec = EvaluateSpec.model_validate(
        {
            **_exact_match_spec(),
            "target": Model(url="http://model.test/v1/chat/completions", name="test-model"),
            "params": RunConfigOnlineModel(parallelism=3),
            "prompt_template": "Question: {{item.question}}",
        }
    )

    compiled = await EvaluateJob.compile(
        workspace="default",
        spec=spec,
        entity_client=object(),
        job_name=None,
        async_sdk=object(),
    )

    job_spec = PlatformJobSpec.model_validate(compiled)
    step = job_spec.steps[0]
    config = cast(dict[str, Any], step.config)
    _assert_metric_step_entrypoint(job_spec)
    assert config["target"]["name"] == "test-model"
    assert config["prompt_template"] == "Question: {{item.question}}"
    assert config["params"]["parallelism"] == 3


async def test_evaluate_job_compile_produces_online_agent_job() -> None:
    spec = EvaluateSpec.model_validate(
        {
            **_exact_match_spec(),
            "target": Agent(
                url="http://agent.test",
                name="test-agent",
                format=AgentFormat.GENERIC,
                body={"question": "{{item.question}}"},
                response_path="$.answer",
            ),
            "prompt_template": {"question": "{{item.question}}"},
        }
    )

    compiled = await EvaluateJob.compile(
        workspace="default",
        spec=spec,
        entity_client=object(),
        job_name=None,
        async_sdk=object(),
    )

    job_spec = PlatformJobSpec.model_validate(compiled)
    step = job_spec.steps[0]
    config = cast(dict[str, Any], step.config)
    _assert_metric_step_entrypoint(job_spec)
    assert config["target"]["name"] == "test-agent"
    assert config["prompt_template"] == {"question": "{{item.question}}"}


async def test_evaluate_job_compile_injects_metric_and_target_secrets() -> None:
    secret_ref = SecretRef(root="NVIDIA_BUILD_API_KEY")
    spec = EvaluateSpec.model_validate(
        {
            **_exact_match_spec(),
            "metric": _bundle_payload(
                LLMJudgeMetric(
                    model=Model(
                        url="https://integrate.api.nvidia.com/v1/chat/completions",
                        name="nvidia/nemotron-3-super-120b-a12b",
                        api_key_secret=secret_ref,
                    ),
                    scores=[
                        RangeScore(
                            name="quality",
                            minimum=1,
                            maximum=5,
                            parser=JSONScoreParser(json_path="quality"),
                        ),
                    ],
                )
            ),
            "target": Model(
                url="https://integrate.api.nvidia.com/v1/chat/completions",
                name="nvidia/nemotron-3-super-120b-a12b",
                api_key_secret=secret_ref,
            ),
            "params": RunConfigOnlineModel(parallelism=3),
            "prompt_template": "Question: {{item.question}}",
        }
    )

    compiled = await EvaluateJob.compile(
        workspace="default",
        spec=spec,
        entity_client=object(),
        job_name=None,
        async_sdk=object(),
    )

    step = PlatformJobSpec.model_validate(compiled).steps[0]
    secrets = {env.name: env.from_secret.name for env in step.environment or [] if env.from_secret}
    assert secrets == {"NVIDIA_BUILD_API_KEY": "NVIDIA_BUILD_API_KEY"}


class TestEvaluateSpec:
    """Validation coverage for evaluator job specs."""

    def test_rejects_empty_dataset(self) -> None:
        with pytest.raises(ValueError, match="List should have at least 1 item"):
            EvaluateSpec.model_validate(
                {
                    **_exact_match_spec(),
                    "dataset": [],
                }
            )

    def test_rejects_legacy_metrics_field(self) -> None:
        with pytest.raises(ValueError, match="metrics|Extra inputs are not permitted"):
            EvaluateSpec.model_validate(
                {
                    "metrics": {
                        "type": "exact-match",
                        "reference": "{{item.expected}}",
                        "candidate": "{{item.model_output}}",
                    },
                    "dataset": _exact_match_spec()["dataset"],
                }
            )

    def test_accepts_metrics_sequence(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "metric": [
                    _exact_match_spec()["metric"],
                    _bundle_payload(F1Metric(reference="{{item.expected}}", candidate="{{item.model_output}}")),
                ],
            }
        )

        assert isinstance(spec.metric, list)
        assert [metric.metric_type for metric in spec.metric] == ["exact-match", "f1"]

    def test_accepts_uppercase_api_key_secret_refs_for_llm_judge_and_target(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                "metric": _bundle_payload(
                    LLMJudgeMetric(
                        model=Model(
                            url="https://integrate.api.nvidia.com/v1/chat/completions",
                            name="nvidia/nemotron-3-super-120b-a12b",
                            api_key_secret=SecretRef(root="NVIDIA_BUILD_API_KEY"),
                        ),
                        scores=[
                            RangeScore(
                                name="quality",
                                minimum=1,
                                maximum=5,
                                parser=JSONScoreParser(json_path="quality"),
                            ),
                        ],
                    )
                ),
                "dataset": [{"prompt": "Hello", "model_output": "Hi"}],
                "target": {
                    "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                    "name": "nvidia/nemotron-3-super-120b-a12b",
                    "api_key_secret": "NVIDIA_BUILD_API_KEY",
                    "format": "nim",
                },
            }
        )

        assert isinstance(spec.metric, MetricBundle)
        assert isinstance(spec.target, Model)
        assert spec.target.api_key_secret is not None
        assert spec.metric.metric_type == "llm-judge"
        assert spec.target.api_key_secret.root == "NVIDIA_BUILD_API_KEY"

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            EvaluateSpec.model_validate(
                {
                    **_exact_match_spec(),
                    "unexpected": "field",
                }
            )

    def test_accepts_serialized_fileset_ref_dataset(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "dataset": "default/helpsteer2#validation/*.jsonl",
            }
        )

        assert spec.dataset == FilesetRef(root="default/helpsteer2#validation/*.jsonl")

    def test_rejects_aggregate_fields_in_params(self) -> None:
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            EvaluateSpec.model_validate(
                {
                    **_exact_match_spec(),
                    "params": {"aggregate_fields": ["mean", "max"]},
                }
            )


class TestEvaluateJobCompile:
    """Branch coverage for the evaluator job compiler."""

    async def test_accepts_equivalent_base_model_spec(self) -> None:
        class EquivalentSpec(BaseModel):
            """Spec shape used to verify compile canonicalizes BaseModel inputs."""

            metric: dict[str, object]
            dataset: list[dict[str, object]]
            params: dict[str, object] | None = None

        compiled = await EvaluateJob.compile(
            workspace="default",
            spec=EquivalentSpec.model_validate(_exact_match_spec()),
            entity_client=object(),
            job_name=None,
            async_sdk=object(),
        )

        job_spec = PlatformJobSpec.model_validate(compiled)
        step = job_spec.steps[0]
        config = cast(dict[str, Any], step.config)
        assert config["metric"]["bundle_kind"] == "metric-bundle"
        assert config["metric"]["metric_type"] == "exact-match"
        assert config["dataset"] == _exact_match_spec()["dataset"]
        assert config["params"]["parallelism"] == 2

    async def test_accepts_metrics_sequence(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "metric": [
                    _exact_match_spec()["metric"],
                    _bundle_payload(F1Metric(reference="{{item.expected}}", candidate="{{item.model_output}}")),
                ],
            }
        )

        compiled = await EvaluateJob.compile(
            workspace="default",
            spec=spec,
            entity_client=object(),
            job_name=None,
            async_sdk=object(),
        )

        config = cast(dict[str, Any], PlatformJobSpec.model_validate(compiled).steps[0].config)
        assert [metric["metric_type"] for metric in config["metric"]] == ["exact-match", "f1"]

    @pytest.mark.parametrize(
        ("target", "expected_message"),
        [
            (
                Model(url="http://model.test/v1/chat/completions", name="test-model"),
                "prompt_template is required when EvaluateSpec.target is a model",
            ),
            (
                Agent(
                    url="http://agent.test",
                    name="test-agent",
                    format=AgentFormat.GENERIC,
                    body={"question": "{{item.question}}"},
                    response_path="$.answer",
                ),
                "prompt_template is required when EvaluateSpec.target is an agent",
            ),
        ],
    )
    async def test_requires_prompt_template_for_online_targets(
        self, target: Model | Agent, expected_message: str
    ) -> None:
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "target": target,
            }
        )

        with pytest.raises(ValueError, match=expected_message):
            await EvaluateJob.compile(
                workspace="default",
                spec=spec,
                entity_client=object(),
                job_name=None,
                async_sdk=object(),
            )

    @pytest.mark.parametrize(
        ("target", "expected_message"),
        [
            (Model(url="http://model.test/v1/chat/completions", name="test-model"), "model target"),
            (
                Agent(
                    url="http://agent.test",
                    name="test-agent",
                    format=AgentFormat.GENERIC,
                    body={"question": "{{item.question}}"},
                    response_path="$.answer",
                ),
                "agent target",
            ),
        ],
    )
    async def test_rejects_wrong_online_param_type(
        self, target: Model | Agent, expected_message: str, mocker: MockerFixture
    ) -> None:
        mocker.patch("nemo_evaluator.jobs.evaluate.normalize_params", return_value=RunConfig())
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "target": target,
                "prompt_template": "Question: {{item.question}}",
            }
        )

        with pytest.raises(TypeError, match=f"{expected_message} requires RunConfigOnline"):
            await EvaluateJob.compile(
                workspace="default",
                spec=spec,
                entity_client=object(),
                job_name=None,
                async_sdk=object(),
            )

    async def test_rejects_wrong_offline_param_type(self, mocker: MockerFixture) -> None:
        mocker.patch("nemo_evaluator.jobs.evaluate.normalize_params", return_value=object())

        with pytest.raises(TypeError, match="offline evaluation requires RunConfig"):
            await EvaluateJob.compile(
                workspace="default",
                spec=EvaluateSpec.model_validate(_exact_match_spec()),
                entity_client=object(),
                job_name=None,
                async_sdk=object(),
            )

    async def test_fileset_ref_dataset_compiles_into_bundle_native_step(self) -> None:
        dataset = FilesetRef(root="default/helpsteer2#validation/*.jsonl")

        compiled = await EvaluateJob.compile(
            workspace="default",
            spec=EvaluateSpec.model_validate({**_exact_match_spec(), "dataset": dataset}),
            entity_client=object(),
            job_name=None,
            async_sdk=object(),
        )

        job_spec = PlatformJobSpec.model_validate(compiled)
        assert [step.name for step in job_spec.steps] == ["dataset-download", "evaluate"]
        download_step = job_spec.steps[0]
        download_container = cast(Any, download_step.executor).container
        assert download_container.entrypoint == ["python", "-m", "nmp.evaluator.tasks.download_fileset"]
        assert download_container.command[-2:] == ["--dataset", dataset.model_dump_json()]
        config = cast(dict[str, Any], job_spec.steps[1].config)
        assert config["dataset"] == dataset.root


class TestEvaluateJobRun:
    """Coverage for the local evaluator job runner."""

    @pytest.mark.parametrize(
        ("spec_overrides", "expected_config_type"),
        [
            ({}, RunConfig),
            (
                {
                    "target": Model(url="http://model.test/v1/chat/completions", name="test-model"),
                    "prompt_template": "Question: {{item.question}}",
                },
                RunConfigOnlineModel,
            ),
            (
                {
                    "target": Agent(
                        url="http://agent.test",
                        name="test-agent",
                        format=AgentFormat.GENERIC,
                        body={"question": "{{item.question}}"},
                        response_path="$.answer",
                    ),
                    "prompt_template": {"question": "{{item.question}}"},
                },
                RunConfigOnline,
            ),
        ],
    )
    def test_delegates_to_sdk_evaluator(
        self,
        spec_overrides: dict[str, object],
        expected_config_type: type[RunConfig],
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        result = _empty_evaluation_result()
        result_payload = result.model_dump(mode="json")
        evaluator = mocker.Mock()
        evaluator.run_sync.return_value = result
        evaluator_cls = mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=evaluator)
        config = {
            **_exact_match_spec(),
            **spec_overrides,
        }
        expected_spec = EvaluateSpec.model_validate(config)
        expected_config = expected_spec.params
        assert isinstance(expected_config, expected_config_type)
        ctx = _make_job_context(tmp_path)

        run_result = EvaluateJob().run(config, ctx=ctx)

        assert run_result == {
            "status": "completed",
            "artifact": run_result["artifact"],
        }
        assert "result" not in run_result
        _assert_saved_result_artifact(run_result, ctx, result_payload)
        evaluator_cls.assert_called_once_with()
        call_kwargs = evaluator.run_sync.call_args.kwargs
        assert isinstance(call_kwargs["metrics"], ExactMatchMetric)
        assert call_kwargs["dataset"] == expected_spec.dataset
        assert call_kwargs["config"] == expected_config
        assert call_kwargs["target"] == expected_spec.target
        assert call_kwargs["prompt_template"] == expected_spec.prompt_template

    def test_delegates_metrics_sequence_to_sdk_evaluator(self, tmp_path: Path, mocker: MockerFixture) -> None:
        result = _empty_evaluation_result()
        result_payload = result.model_dump(mode="json")
        evaluator = mocker.Mock()
        evaluator.run_sync.return_value = result
        evaluator_cls = mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=evaluator)
        config = {
            **_exact_match_spec(),
            "metric": [
                _exact_match_spec()["metric"],
                _bundle_payload(F1Metric(reference="{{item.expected}}", candidate="{{item.model_output}}")),
            ],
        }
        expected_spec = EvaluateSpec.model_validate(config)
        ctx = _make_job_context(tmp_path)

        run_result = EvaluateJob().run(config, ctx=ctx)

        assert run_result == {
            "status": "completed",
            "artifact": run_result["artifact"],
        }
        assert "result" not in run_result
        _assert_saved_result_artifact(run_result, ctx, result_payload)
        evaluator_cls.assert_called_once_with()
        call_kwargs = evaluator.run_sync.call_args.kwargs
        assert [metric.type.value for metric in call_kwargs["metrics"]] == ["exact-match", "f1"]
        assert call_kwargs["dataset"] == expected_spec.dataset
        assert call_kwargs["config"] == expected_spec.params
        assert call_kwargs["target"] == expected_spec.target
        assert call_kwargs["prompt_template"] == expected_spec.prompt_template

    def test_downloads_fileset_ref_dataset_and_passes_path_to_sdk_evaluator(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        result = _empty_evaluation_result()
        result_payload = result.model_dump(mode="json")
        evaluator = mocker.Mock()
        evaluator.run_sync.return_value = result
        mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=evaluator)
        downloaded_path = tmp_path / "persistent" / "dataset" / "default" / "helpsteer2" / "validation.jsonl"
        download_dataset = mocker.patch(
            "nemo_evaluator.jobs.utils.download_dataset",
            new=mocker.AsyncMock(return_value=downloaded_path),
            create=True,
        )
        download_dataset_sync = mocker.patch("nemo_evaluator.jobs.utils.download_dataset_sync", create=True)
        ctx = _make_job_context(tmp_path)
        async_sdk = object()
        dataset = FilesetRef(root="default/helpsteer2#validation.jsonl")
        config = {**_exact_match_spec(), "dataset": dataset}

        run_result = EvaluateJob().run(config, ctx=ctx, async_sdk=async_sdk)

        _assert_saved_result_artifact(run_result, ctx, result_payload)
        download_dataset.assert_awaited_once_with(
            sdk=async_sdk,
            dataset=dataset,
            destination=str(ctx.storage.persistent / "dataset"),
        )
        download_dataset_sync.assert_not_called()
        call_kwargs = evaluator.run_sync.call_args.kwargs
        assert isinstance(call_kwargs["metrics"], ExactMatchMetric)
        assert call_kwargs["dataset"] == downloaded_path
        assert call_kwargs["config"] == EvaluateSpec.model_validate(config).params
        assert call_kwargs["target"] is None
        assert call_kwargs["prompt_template"] is None

    def test_downloads_fileset_ref_dataset_with_sync_sdk_and_passes_path_to_sdk_evaluator(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        result = _empty_evaluation_result()
        result_payload = result.model_dump(mode="json")
        evaluator = mocker.Mock()
        evaluator.run_sync.return_value = result
        mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=evaluator)
        downloaded_path = tmp_path / "persistent" / "dataset" / "default" / "helpsteer2" / "validation.jsonl"
        download_dataset = mocker.patch("nemo_evaluator.jobs.utils.download_dataset", create=True)
        download_dataset_sync = mocker.patch(
            "nemo_evaluator.jobs.utils.download_dataset_sync",
            return_value=downloaded_path,
            create=True,
        )
        ctx = _make_job_context(tmp_path)
        sync_sdk = object()
        dataset = FilesetRef(root="default/helpsteer2#validation.jsonl")
        config = {**_exact_match_spec(), "dataset": dataset}

        run_result = EvaluateJob().run(config, ctx=ctx, sdk=sync_sdk)

        _assert_saved_result_artifact(run_result, ctx, result_payload)
        download_dataset.assert_not_called()
        download_dataset_sync.assert_called_once_with(
            sdk=sync_sdk,
            dataset=dataset,
            destination=str(ctx.storage.persistent / "dataset"),
        )
        call_kwargs = evaluator.run_sync.call_args.kwargs
        assert isinstance(call_kwargs["metrics"], ExactMatchMetric)
        assert call_kwargs["dataset"] == downloaded_path
        assert call_kwargs["config"] == EvaluateSpec.model_validate(config).params
        assert call_kwargs["target"] is None
        assert call_kwargs["prompt_template"] is None


class TestEvaluateTask:
    """Coverage for the compiled container task entrypoint."""

    def test_main_dispatches_evaluate_job_with_task_sdk(self, mocker: MockerFixture) -> None:
        sdk = object()
        get_task_sdk = mocker.patch("nemo_evaluator.tasks.evaluate.get_task_sdk", return_value=sdk)
        run_task = mocker.patch("nemo_evaluator.tasks.evaluate.run_task", return_value=0)

        exit_code = evaluate_task_main()

        assert exit_code == 0
        get_task_sdk.assert_called_once_with("evaluator")
        run_task.assert_called_once_with(EvaluateJob, sdk=sdk)
