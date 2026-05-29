# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the evaluator plugin's SDK-backed job."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
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
from nemo_evaluator.resolvers import PlatformModelResolver, _parse_required_workspace_name
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.protocol import MetricOutput, MetricResult
from nemo_evaluator_sdk.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.models import ModelRef
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
        "metric": {
            "type": "exact-match",
            "reference": "{{item.expected}}",
            "candidate": "{{item.model_output}}",
        },
        "dataset": [
            {"expected": "blue", "model_output": "Blue"},
            {"expected": "Jupiter", "model_output": "Saturn"},
        ],
        "params": {"parallelism": 2},
    }


def _assert_metric_step_entrypoint(job_spec: PlatformJobSpec) -> None:
    step = job_spec.steps[0]
    container = cast(Any, step.executor).container
    assert container.entrypoint == ["python", "-m", "nmp.evaluator.tasks.evaluate_metric"]
    command = container.command
    assert command is not None
    assert command == [
        "--progress-tracking-url",
        "${NMP_JOBS_URL}/apis/jobs/v2/workspaces/${NEMO_JOB_WORKSPACE}/jobs/${NEMO_JOB_ID}/status-details",
    ]


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
    results_dir = ctx.storage.persistent / "results"
    assert (
        json.loads((results_dir / AGGREGATE_SCORES_RESULT_NAME).read_text(encoding="utf-8"))
        == result_payload["aggregate_scores"]
    )
    assert (results_dir / ROW_SCORES_RESULT_NAME).read_text(encoding="utf-8") == ""
    assert (results_dir / ARTIFACTS_RESULT_NAME).is_dir()


def _mock_evaluation_result(mocker: MockerFixture, result_payload: dict[str, object]) -> Any:
    """Return an evaluator result mock with platform result artifact surfaces."""
    result = mocker.Mock()
    result.model_dump.return_value = result_payload
    aggregate_scores = mocker.Mock()
    aggregate_scores.model_dump_json.return_value = json.dumps(result_payload["aggregate_scores"], indent=2)
    result.aggregate_scores = aggregate_scores
    result.row_scores = []
    return result


def _load_artifact_payload(run_result: dict[str, Any]) -> dict[str, Any]:
    """Load a local artifact payload from a scheduler or CLI run result."""
    artifact_path = Path(run_result["artifact"]["artifact_url"].removeprefix("file://"))
    return cast(dict[str, Any], json.loads(artifact_path.read_text(encoding="utf-8")))


class _FakeModels:
    def __init__(self) -> None:
        self.retrieved: list[tuple[str, str]] = []

    def retrieve(self, name: str, *, workspace: str) -> SimpleNamespace:
        self.retrieved.append((workspace, name))
        return SimpleNamespace(model_providers=["default/provider"])

    def get_model_entity_route_openai_url(self, model_entity: object) -> str:
        del model_entity
        return "https://igw.example.test/v1/chat/completions"


class _FakeProviders:
    def retrieve(self, name: str, *, workspace: str) -> SimpleNamespace:
        return SimpleNamespace(name=name, workspace=workspace, host_url="http://nim.example.test:8000")


class _FakeSDK:
    def __init__(self) -> None:
        self.models = _FakeModels()
        self.inference = SimpleNamespace(providers=_FakeProviders())


def _llm_judge_ref_metric() -> LLMJudgeMetric:
    return LLMJudgeMetric(
        model=ModelRef(root="default/judge"),
        scores=[
            RangeScore(
                name="quality",
                minimum=0,
                maximum=1,
                parser=JSONScoreParser(json_path="quality"),
            )
        ],
    )


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


async def test_platform_model_resolver_resolves_model_ref_through_sdk() -> None:
    sdk = _FakeSDK()
    resolver = PlatformModelResolver(sdk)

    model = await resolver.resolve_model(ModelRef(root="default/judge"))

    assert sdk.models.retrieved == [("default", "judge")]
    assert model.name == "judge"
    assert model.url == "https://igw.example.test/v1/chat/completions"
    assert model.host_url == "http://nim.example.test:8000"


def test_parse_required_workspace_name_rejects_extra_separator() -> None:
    with pytest.raises(ValueError, match="ModelRef must be in format 'workspace/model_name'"):
        _parse_required_workspace_name("default/judge/extra", label="ModelRef", expected_format="workspace/model_name")


def test_evaluate_job_resolves_metric_model_refs_before_sdk_run(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    async def compute_scores(metric: LLMJudgeMetric, input) -> MetricResult:
        del input
        assert isinstance(metric.model, Model)
        assert metric.model.name == "judge"
        assert metric.model.host_url == "http://nim.example.test:8000"
        return MetricResult(outputs=[MetricOutput(name="quality", value=1.0)])

    mocker.patch.object(LLMJudgeMetric, "preflight", mocker.AsyncMock(return_value=None))
    mocker.patch.object(LLMJudgeMetric, "compute_scores", compute_scores)

    ctx = _make_job_context(tmp_path)
    run_result = EvaluateJob().run(
        {
            "metric": _llm_judge_ref_metric().model_dump(mode="json"),
            "dataset": [{"output_text": "hello"}],
        },
        ctx=ctx,
        sdk=_FakeSDK(),
    )

    payload = _load_artifact_payload(run_result)
    assert payload["aggregate_scores"]["scores"][0]["name"] == "llm-judge.quality"
    assert payload["aggregate_scores"]["scores"][0]["mean"] == 1.0


def test_evaluate_job_rejects_model_refs_without_platform_sdk(tmp_path: Path) -> None:
    ctx = _make_job_context(tmp_path)

    with pytest.raises(ValueError, match="ModelRef metrics require `sdk` or `async_sdk`"):
        EvaluateJob().run(
            {
                "metric": _llm_judge_ref_metric().model_dump(mode="json"),
                "dataset": [{"output_text": "hello"}],
            },
            ctx=ctx,
        )


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
    assert step.name == "evaluation"
    _assert_metric_step_entrypoint(job_spec)
    assert step.config is not None
    config = cast(dict[str, Any], step.config)
    assert config["metric"]["type"] == "exact-match"
    assert config["dataset"]["rows"] == _exact_match_spec()["dataset"]


async def test_evaluate_job_compile_resolves_metric_model_refs_before_remote_job() -> None:
    compiled = await EvaluateJob.compile(
        workspace="default",
        spec=EvaluateSpec.model_validate(
            {
                "metric": _llm_judge_ref_metric().model_dump(mode="json"),
                "dataset": [{"output_text": "hello"}],
            }
        ),
        entity_client=object(),
        job_name=None,
        async_sdk=_FakeSDK(),
    )

    job_spec = PlatformJobSpec.model_validate(compiled)
    config = cast(dict[str, Any], job_spec.steps[0].config)
    assert config["metric"]["model"]["name"] == "judge"
    assert config["metric"]["model"]["url"] == "https://igw.example.test/v1/chat/completions"
    assert config["metric"]["model"]["host_url"] == "http://nim.example.test:8000"


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
    assert config["model"]["name"] == "test-model"
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
    assert config["agent"]["name"] == "test-agent"
    assert config["prompt_template"] == {"question": "{{item.question}}"}


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
                    {
                        "type": "f1",
                        "reference": "{{item.expected}}",
                        "candidate": "{{item.model_output}}",
                    },
                ],
            }
        )

        assert isinstance(spec.metric, list)
        assert [metric.type.value for metric in spec.metric] == ["exact-match", "f1"]

    def test_accepts_uppercase_api_key_secret_refs_for_llm_judge_and_target(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                "metric": {
                    "type": "llm-judge",
                    "model": {
                        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                        "name": "nvidia/nemotron-3-super-120b-a12b",
                        "api_key_secret": "NVIDIA_BUILD_API_KEY",
                        "format": "nim",
                    },
                    "scores": [
                        {
                            "name": "quality",
                            "minimum": 1,
                            "maximum": 5,
                            "parser": {"type": "json", "json_path": "quality"},
                        },
                    ],
                },
                "dataset": [{"prompt": "Hello", "model_output": "Hi"}],
                "target": {
                    "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                    "name": "nvidia/nemotron-3-super-120b-a12b",
                    "api_key_secret": "NVIDIA_BUILD_API_KEY",
                    "format": "nim",
                },
            }
        )

        assert isinstance(spec.metric, LLMJudgeMetric)
        assert isinstance(spec.metric.model, Model)
        assert isinstance(spec.target, Model)
        assert spec.metric.model.api_key_secret is not None
        assert spec.target.api_key_secret is not None
        assert spec.metric.model.api_key_secret.root == "NVIDIA_BUILD_API_KEY"
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
        assert config["metric"]["type"] == "exact-match"
        assert config["dataset"]["rows"] == _exact_match_spec()["dataset"]
        assert config["params"]["parallelism"] == 2

    async def test_rejects_remote_compile_for_metrics_sequence(self) -> None:
        spec = EvaluateSpec.model_validate(
            {
                **_exact_match_spec(),
                "metric": [
                    _exact_match_spec()["metric"],
                    {
                        "type": "f1",
                        "reference": "{{item.expected}}",
                        "candidate": "{{item.model_output}}",
                    },
                ],
            }
        )

        with pytest.raises(NotImplementedError, match="Remote benchmark.*not implemented"):
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

    async def test_fileset_ref_dataset_validates_and_compiles_with_download_step(self, mocker: MockerFixture) -> None:
        dataset = FilesetRef(root="default/helpsteer2#validation/*.jsonl")
        dataset_exists = mocker.patch(
            "nemo_evaluator.jobs.utils.dataset_exists",
            new=mocker.AsyncMock(return_value=True),
            create=True,
        )
        async_sdk = object()

        compiled = await EvaluateJob.compile(
            workspace="default",
            spec=EvaluateSpec.model_validate({**_exact_match_spec(), "dataset": dataset}),
            entity_client=object(),
            job_name=None,
            async_sdk=async_sdk,
        )

        job_spec = PlatformJobSpec.model_validate(compiled)
        assert [step.name for step in job_spec.steps] == ["dataset-download", "evaluation"]
        config = cast(dict[str, Any], job_spec.steps[1].config)
        assert config["dataset"] == dataset.root
        assert config["dataset_ref"] == dataset.root
        dataset_exists.assert_awaited_once_with(async_sdk, dataset)

    async def test_fileset_ref_dataset_compile_raises_when_dataset_does_not_exist(self, mocker: MockerFixture) -> None:
        dataset = FilesetRef(root="default/missing")
        dataset_exists = mocker.patch(
            "nemo_evaluator.jobs.utils.dataset_exists",
            new=mocker.AsyncMock(return_value=False),
            create=True,
        )
        async_sdk = object()

        with pytest.raises(ValueError, match="FilesetRef dataset does not exist: default/missing"):
            await EvaluateJob.compile(
                workspace="default",
                spec=EvaluateSpec.model_validate({**_exact_match_spec(), "dataset": dataset}),
                entity_client=object(),
                job_name=None,
                async_sdk=async_sdk,
            )

        dataset_exists.assert_awaited_once_with(async_sdk, dataset)


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
        result_payload = {"aggregate_scores": {"scores": []}}
        result = _mock_evaluation_result(mocker, result_payload)
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
        evaluator.run_sync.assert_called_once_with(
            metrics=expected_spec.metric,
            dataset=expected_spec.dataset,
            config=expected_config,
            target=expected_spec.target,
            prompt_template=expected_spec.prompt_template,
        )
        result.model_dump.assert_called_once_with(mode="json")

    def test_delegates_metrics_sequence_to_sdk_evaluator(self, tmp_path: Path, mocker: MockerFixture) -> None:
        result_payload = {
            "row_scores": [],
            "aggregate_scores": {"scores": []},
            "per_metric": {},
        }
        result = _mock_evaluation_result(mocker, result_payload)
        evaluator = mocker.Mock()
        evaluator.run_sync.return_value = result
        evaluator_cls = mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=evaluator)
        config = {
            **_exact_match_spec(),
            "metric": [
                _exact_match_spec()["metric"],
                {
                    "type": "f1",
                    "reference": "{{item.expected}}",
                    "candidate": "{{item.model_output}}",
                },
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
        evaluator.run_sync.assert_called_once_with(
            metrics=expected_spec.metric,
            dataset=expected_spec.dataset,
            config=expected_spec.params,
            target=expected_spec.target,
            prompt_template=expected_spec.prompt_template,
        )
        result.model_dump.assert_called_once_with(mode="json")

    def test_downloads_fileset_ref_dataset_and_passes_path_to_sdk_evaluator(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        result_payload = {"aggregate_scores": {"scores": []}}
        result = _mock_evaluation_result(mocker, result_payload)
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
        evaluator.run_sync.assert_called_once_with(
            metrics=EvaluateSpec.model_validate(config).metric,
            dataset=downloaded_path,
            config=EvaluateSpec.model_validate(config).params,
            target=None,
            prompt_template=None,
        )
        result.model_dump.assert_called_once_with(mode="json")

    def test_downloads_fileset_ref_dataset_with_sync_sdk_and_passes_path_to_sdk_evaluator(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        result_payload = {"aggregate_scores": {"scores": []}}
        result = _mock_evaluation_result(mocker, result_payload)
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
        evaluator.run_sync.assert_called_once_with(
            metrics=EvaluateSpec.model_validate(config).metric,
            dataset=downloaded_path,
            config=EvaluateSpec.model_validate(config).params,
            target=None,
            prompt_template=None,
        )
        result.model_dump.assert_called_once_with(mode="json")
