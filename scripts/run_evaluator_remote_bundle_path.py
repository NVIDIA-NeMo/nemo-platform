# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke-test evaluator plugin remote execution with bundled metrics."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
from nemo_evaluator.sdk._executor import _build_evaluate_spec
from nemo_evaluator.sdk.resources import Evaluator as PluginEvaluator
from nemo_evaluator.sdk.standalone_sdk.backend import NMPBackend
from nemo_evaluator_sdk import Evaluator as SDKEvaluator
from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.metrics.bleu import BLEUMetric
from nemo_evaluator_sdk.metrics.cloudpickle import CloudpickleMetricBundler
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.number_check import NumberCheckMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.metrics.ragas import (
    AgentGoalAccuracyMetric,
    AnswerAccuracyMetric,
    ContextEntityRecallMetric,
    ContextPrecisionMetric,
    ContextRecallMetric,
    ContextRelevanceMetric,
    FaithfulnessMetric,
    NoiseSensitivityMetric,
    ResponseGroundednessMetric,
    ResponseRelevancyMetric,
    ToolCallAccuracyMetric,
    TopicAdherenceMetric,
)
from nemo_evaluator_sdk.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric
from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.metrics.tool_calling import ToolCallingMetric
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfig, SecretRef
from nemo_evaluator_sdk.values.scores import JSONScoreParser, RangeScore, RemoteScore
from nemo_platform import NeMoPlatform
from openai import AsyncOpenAI

DatasetRow = dict[str, object]


@dataclass(frozen=True)
class MetricCase:
    name: str
    metric: Metric
    expected_aggregate_scores: tuple[str, ...]


class CustomContainsMetric:
    type = "custom-contains"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("contains")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        expected = str(input.row.data["expected"]).lower()
        candidate = str(input.row.data["model_output"]).lower()
        return MetricResult(outputs=[MetricOutput(name="contains", value=float(expected in candidate))])


async def _fake_judge_inference(
    model: Model,
    request: dict,
    max_retries: int | None,
    *,
    client: AsyncOpenAI | None = None,
    api_key: str | None = None,
    default_headers: dict | None = None,
    timeout: float | None = None,
) -> dict:
    del model, request, max_retries, client, api_key, default_headers, timeout
    return {"choices": [{"message": {"content": json.dumps({"helpfulness": 4})}}]}


class _RemoteMetricHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        request = json.loads(raw_body.decode("utf-8"))
        if request.get("evaluator_name") == "nat-quality":
            response = {"result": {"score": 0.9}}
        else:
            response = {"result": {"quality": 0.75}}
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def _remote_metric_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RemoteMetricHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _base_url() -> str:
    return os.environ.get("NEMO_PLATFORM_BASE_URL", "http://127.0.0.1:8080")


def _workspace() -> str:
    return os.environ.get("NEMO_PLATFORM_WORKSPACE", "default")


def _poll_interval_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_POLL_INTERVAL_SECONDS", "2"))


def _job_timeout_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_JOB_TIMEOUT_SECONDS", "600"))


def _pending_timeout_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_PENDING_TIMEOUT_SECONDS", "120"))


def _live_nvidia_enabled() -> bool:
    return os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_NVIDIA") == "1"


def _nvidia_secret_ref() -> SecretRef:
    return SecretRef(root=os.environ.get("NEMO_EVALUATOR_SMOKE_NVIDIA_SECRET", "nvidia-api-key"))


def _ensure_live_nvidia_secret(platform: NeMoPlatform) -> None:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NEMO_EVALUATOR_SMOKE_LIVE_NVIDIA=1 requires NVIDIA_API_KEY in the script environment")

    secret_name = _nvidia_secret_ref().root
    try:
        platform.secrets.retrieve(secret_name, workspace=_workspace())
    except Exception:
        platform.secrets.create(name=secret_name, value=api_key, workspace=_workspace())
    else:
        platform.secrets.update(secret_name, value=api_key, workspace=_workspace())


def _nvidia_judge_model() -> Model:
    return Model(
        url=os.environ.get(
            "NEMO_EVALUATOR_SMOKE_NVIDIA_CHAT_URL",
            "https://integrate.api.nvidia.com/v1/chat/completions",
        ),
        name=os.environ.get("NEMO_EVALUATOR_SMOKE_NVIDIA_JUDGE_MODEL", "meta/llama-3.1-70b-instruct"),
        api_key_secret=_nvidia_secret_ref(),
        format=ModelFormat.NVIDIA_NIM,
    )


def _nvidia_embeddings_model() -> Model:
    return Model(
        url=os.environ.get(
            "NEMO_EVALUATOR_SMOKE_NVIDIA_EMBEDDINGS_URL",
            "https://integrate.api.nvidia.com/v1/embeddings",
        ),
        name=os.environ.get("NEMO_EVALUATOR_SMOKE_NVIDIA_EMBEDDINGS_MODEL", "nvidia/nv-embedqa-e5-v5"),
        api_key_secret=_nvidia_secret_ref(),
        format=ModelFormat.NVIDIA_NIM,
    )


def _live_llm_inference_params() -> InferenceParams:
    return InferenceParams(
        temperature=0.0,
        max_tokens=int(os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_MAX_TOKENS", "512")),
    )


def _live_ragas_inference_params() -> InferenceParams:
    return InferenceParams.model_validate(
        {
            "temperature": 0.0,
            "max_tokens": int(os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_MAX_TOKENS", "512")),
            "request_timeout": float(os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_REQUEST_TIMEOUT_SECONDS", "90")),
            "max_retries": int(os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_MAX_RETRIES", "0")),
            "max_workers": int(os.environ.get("NEMO_EVALUATOR_SMOKE_LIVE_MAX_WORKERS", "1")),
        }
    )


def _dataset() -> list[DatasetRow]:
    return [
        {
            "expected": "blue",
            "model_output": "Blue",
            "left_text": "prefix needle suffix",
            "right_text": "needle",
            "left_number": "42",
            "right_number": "42",
            "expected_tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_weather", "arguments": {"city": "Halifax"}},
                }
            ],
            "response": {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": '{"city": "Halifax"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        },
        {
            "expected": "Jupiter",
            "model_output": "Jupiter is the largest planet",
            "left_text": "another haystack with needle",
            "right_text": "needle",
            "left_number": "7.5",
            "right_number": "7.5",
            "expected_tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "lookup_planet", "arguments": {"name": "Jupiter"}},
                }
            ],
            "response": {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_planet",
                                        "arguments": '{"name": "Jupiter"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        },
    ]


def _judge_model() -> Model:
    return Model(
        url="https://judge.example.test/v1/chat/completions",
        name="judge-model",
        format=ModelFormat.OPEN_AI,
    )


def _embeddings_model() -> Model:
    return Model(
        url="https://judge.example.test/v1/embeddings",
        name="embedding-model",
        format=ModelFormat.OPEN_AI,
    )


def _llm_judge_metric() -> LLMJudgeMetric:
    metric = LLMJudgeMetric(
        model=_judge_model(),
        scores=[
            RangeScore(
                name="helpfulness",
                minimum=1,
                maximum=5,
                parser=JSONScoreParser(json_path="helpfulness"),
            )
        ],
        prompt_template="Judge: {{item.expected}} -> {{item.model_output}}",
    )
    metric.set_inference_fn(_fake_judge_inference)
    return metric


def _live_llm_judge_metric() -> LLMJudgeMetric:
    return LLMJudgeMetric(
        model=_nvidia_judge_model(),
        scores=[
            RangeScore(
                name="correctness",
                minimum=1,
                maximum=5,
                parser=JSONScoreParser(json_path="correctness"),
            )
        ],
        prompt_template={
            "messages": [
                {
                    "role": "system",
                    "content": "Score the candidate against the expected answer. Return only JSON.",
                },
                {
                    "role": "user",
                    "content": "Expected: {{item.expected}}\nCandidate: {{item.model_output}}",
                },
            ]
        },
        inference=_live_llm_inference_params(),
    )


def _live_rag_dataset() -> list[DatasetRow]:
    return [
        {
            "user_input": "What is the capital of France?",
            "retrieved_contexts": [
                "Paris is the capital and largest city of France.",
                "Berlin is the capital of Germany.",
            ],
            "response": "The capital of France is Paris.",
            "reference": "Paris is the capital of France.",
        }
    ]


def _live_agentic_dataset() -> list[DatasetRow]:
    return [
        {
            "user_input": [
                {"content": "What's the weather in Paris?", "type": "human"},
                {
                    "content": "Let me check.",
                    "type": "ai",
                    "tool_calls": [{"name": "weather_api", "args": {"city": "Paris"}}],
                },
                {"content": "Sunny, 22C", "type": "tool"},
                {"content": "It's sunny and 22C in Paris.", "type": "ai"},
            ],
            "reference": "The agent checked the weather for Paris and reported the result.",
            "reference_tool_calls": [{"name": "weather_api", "args": {"city": "Paris"}}],
            "reference_topics": ["weather", "Paris"],
        }
    ]


def _live_rag_metric_cases() -> list[MetricCase]:
    judge_model = _nvidia_judge_model()
    inference = _live_ragas_inference_params()
    return [
        MetricCase("answer_accuracy", AnswerAccuracyMetric(judge_model=judge_model, inference=inference), ()),
        MetricCase("context_relevance", ContextRelevanceMetric(judge_model=judge_model, inference=inference), ()),
        MetricCase(
            "response_groundedness",
            ResponseGroundednessMetric(judge_model=judge_model, inference=inference),
            (),
        ),
        MetricCase("context_recall", ContextRecallMetric(judge_model=judge_model, inference=inference), ()),
        MetricCase("context_precision", ContextPrecisionMetric(judge_model=judge_model, inference=inference), ()),
        MetricCase(
            "context_entity_recall", ContextEntityRecallMetric(judge_model=judge_model, inference=inference), ()
        ),
        MetricCase(
            "response_relevancy",
            ResponseRelevancyMetric(
                judge_model=judge_model,
                embeddings_model=_nvidia_embeddings_model(),
                inference=inference,
                strictness=1,
            ),
            (),
        ),
        MetricCase("faithfulness", FaithfulnessMetric(judge_model=judge_model, inference=inference), ()),
        MetricCase("noise_sensitivity", NoiseSensitivityMetric(judge_model=judge_model, inference=inference), ()),
    ]


def _live_agentic_metric_cases() -> list[MetricCase]:
    judge_model = _nvidia_judge_model()
    inference = _live_ragas_inference_params()
    return [
        MetricCase(
            "topic_adherence",
            TopicAdherenceMetric(metric_mode="f1", judge_model=judge_model, inference=inference),
            (),
        ),
        MetricCase("tool_call_accuracy", ToolCallAccuracyMetric(), ()),
        MetricCase(
            "agent_goal_accuracy",
            AgentGoalAccuracyMetric(use_reference=True, judge_model=judge_model, inference=inference),
            (),
        ),
    ]


def _bundle_only_metric_cases() -> list[MetricCase]:
    judge_model = _judge_model()
    return [
        MetricCase("topic_adherence", TopicAdherenceMetric(metric_mode="f1", judge_model=judge_model), ()),
        MetricCase("tool_call_accuracy", ToolCallAccuracyMetric(), ()),
        MetricCase("agent_goal_accuracy", AgentGoalAccuracyMetric(judge_model=judge_model), ()),
        MetricCase("answer_accuracy", AnswerAccuracyMetric(judge_model=judge_model), ()),
        MetricCase("context_relevance", ContextRelevanceMetric(judge_model=judge_model), ()),
        MetricCase("response_groundedness", ResponseGroundednessMetric(judge_model=judge_model), ()),
        MetricCase("context_recall", ContextRecallMetric(judge_model=judge_model), ()),
        MetricCase("context_precision", ContextPrecisionMetric(judge_model=judge_model), ()),
        MetricCase("context_entity_recall", ContextEntityRecallMetric(judge_model=judge_model), ()),
        MetricCase(
            "response_relevancy",
            ResponseRelevancyMetric(judge_model=judge_model, embeddings_model=_embeddings_model()),
            (),
        ),
        MetricCase("faithfulness", FaithfulnessMetric(judge_model=judge_model), ()),
        MetricCase("noise_sensitivity", NoiseSensitivityMetric(judge_model=judge_model), ()),
    ]


def _metric_cases(remote_metric_url: str) -> list[MetricCase]:
    return [
        MetricCase(
            name="exact_match",
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=("exact-match.exact-match",),
        ),
        MetricCase(
            name="f1",
            metric=F1Metric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=("f1.f1",),
        ),
        MetricCase(
            name="bleu",
            metric=BLEUMetric(references=["{{item.expected}}"], candidate="{{item.model_output}}"),
            expected_aggregate_scores=("bleu.sentence", "bleu.corpus"),
        ),
        MetricCase(
            name="rouge",
            metric=ROUGEMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=(
                "rouge.rouge_1_score",
                "rouge.rouge_2_score",
                "rouge.rouge_3_score",
                "rouge.rouge_L_score",
            ),
        ),
        MetricCase(
            name="string_check",
            metric=StringCheckMetric(
                operation="contains",
                left_template="{{item.left_text}}",
                right_template="{{item.right_text}}",
            ),
            expected_aggregate_scores=("string-check.string-check",),
        ),
        MetricCase(
            name="number_check",
            metric=NumberCheckMetric(
                operation="equals",
                left_template="{{item.left_number}}",
                right_template="{{item.right_number}}",
            ),
            expected_aggregate_scores=("number-check.number-check",),
        ),
        MetricCase(
            name="tool_calling",
            metric=ToolCallingMetric(reference="{{item.expected_tool_calls}}"),
            expected_aggregate_scores=(
                "tool-calling.function_name_accuracy",
                "tool-calling.function_name_and_args_accuracy",
            ),
        ),
        MetricCase(
            name="custom_protocol",
            metric=CustomContainsMetric(),
            expected_aggregate_scores=("custom-contains.contains",),
        ),
        MetricCase(
            name="llm_judge",
            metric=_llm_judge_metric(),
            expected_aggregate_scores=("llm-judge.helpfulness",),
        ),
        MetricCase(
            name="remote",
            metric=RemoteMetric(
                url=remote_metric_url,
                body={"prompt": "{{item.expected}}", "candidate": "{{item.model_output}}"},
                scores=[RemoteScore(name="quality", parser=JSONScoreParser(json_path="$.result.quality"))],
                max_retries=0,
            ),
            expected_aggregate_scores=("remote.quality",),
        ),
        MetricCase(
            name="nemo_agent_toolkit_remote",
            metric=NemoAgentToolkitRemoteMetric(
                url=remote_metric_url,
                evaluator_name="nat-quality",
                max_retries=0,
            ),
            expected_aggregate_scores=("nemo-agent-toolkit-remote.nat-quality",),
        ),
    ]


def _aggregate_score_names(result) -> list[str]:
    return [score.name for score in result.aggregate_scores.scores]


def _expected_names(metric_cases: Sequence[MetricCase]) -> list[str]:
    return [
        f"{metric_type_name(metric_case.metric)}.{output.name}"
        for metric_case in metric_cases
        for output in metric_case.metric.output_spec()
    ]


def _assert_bundle_round_trips(metric_cases: Sequence[MetricCase], bundler: CloudpickleMetricBundler) -> None:
    for metric_case in metric_cases:
        bundle = bundler.bundle(metric_case.metric)
        hydrated = bundler.unbundle(bundle)
        if [output.name for output in hydrated.output_spec()] != [
            output.name for output in metric_case.metric.output_spec()
        ]:
            raise AssertionError(f"bundle round trip changed output spec for {metric_case.name}")


def _assert_scores_present(actual: Sequence[str], expected: Sequence[str]) -> None:
    missing = [score_name for score_name in expected if score_name not in actual]
    if missing:
        raise AssertionError(f"missing aggregate scores {missing}; actual scores: {list(actual)}")


def _assert_no_metric_errors(result, label: str) -> None:
    errors = [row_score.metric_errors for row_score in result.row_scores if row_score.metric_errors]
    if errors:
        raise AssertionError(f"{label} had row metric errors: {errors}")


def _assert_no_all_nan_scores(result, label: str) -> None:
    all_nan_scores = [
        score.name for score in result.aggregate_scores.scores if score.count > 0 and score.nan_count == score.count
    ]
    if all_nan_scores:
        raise AssertionError(f"{label} produced only NaN values for scores: {all_nan_scores}")


def _run_live_metric_job(
    *,
    plugin_resource: PluginEvaluator,
    bundler: CloudpickleMetricBundler,
    label: str,
    metric_cases: Sequence[MetricCase],
    dataset: list[DatasetRow],
):
    spec = _build_evaluate_spec(
        metrics=[metric_case.metric for metric_case in metric_cases],
        request=EvaluationRequest(dataset=dataset, params=RunConfig(parallelism=1)),
        metric_bundler=bundler,
    )
    job = plugin_resource._executor.create(spec=spec, workspace=_workspace())
    job.wait_until_done(
        poll_interval_seconds=_poll_interval_seconds(),
        job_timeout_seconds=_job_timeout_seconds(),
        pending_timeout_seconds=_pending_timeout_seconds(),
    )
    result = job.get_result()
    score_names = _aggregate_score_names(result)
    _assert_scores_present(score_names, _expected_names(metric_cases))
    _assert_no_metric_errors(result, label)
    _assert_no_all_nan_scores(result, label)
    print(f"{label}_job={job.name}")
    print(f"{label}_scores={score_names}")
    print(f"{label}_means={[score.mean for score in result.aggregate_scores.scores]}")
    return result


def main() -> int:
    dataset = _dataset()
    config = RunConfig(parallelism=2)
    bundler = CloudpickleMetricBundler()

    with _remote_metric_server() as remote_metric_url, httpx.Client(timeout=httpx.Timeout(30.0)) as http_client:
        metric_cases = _metric_cases(remote_metric_url)
        bundle_only_metric_cases = _bundle_only_metric_cases()
        _assert_bundle_round_trips([*metric_cases, *bundle_only_metric_cases], bundler)
        platform = NeMoPlatform(
            base_url=_base_url(),
            workspace=_workspace(),
            http_client=http_client,
        )
        plugin_resource = PluginEvaluator(platform)
        backend = NMPBackend(
            plugin_resource,
            execution_mode="remote",
            metric_bundler=bundler,
        )
        evaluator = SDKEvaluator(client=backend)
        if _live_nvidia_enabled():
            _ensure_live_nvidia_secret(platform)

        exact_result = evaluator.run_sync(
            metrics=metric_cases[0].metric,
            dataset=dataset,
            config=config,
        )
        exact_score = exact_result.aggregate_scores.scores[0]
        custom_result = evaluator.run_sync(
            metrics=CustomContainsMetric(),
            dataset=dataset,
            config=config,
        )
        custom_score = custom_result.aggregate_scores.scores[0]

        multi_spec = _build_evaluate_spec(
            metrics=[metric_case.metric for metric_case in metric_cases],
            request=EvaluationRequest(dataset=dataset, params=config),
            metric_bundler=bundler,
        )
        multi_job = plugin_resource._executor.create(spec=multi_spec, workspace=_workspace())
        multi_job.wait_until_done(
            poll_interval_seconds=_poll_interval_seconds(),
            job_timeout_seconds=_job_timeout_seconds(),
            pending_timeout_seconds=_pending_timeout_seconds(),
        )
        multi_result = multi_job.get_result()

        print(f"exact_rows={len(exact_result.row_scores)}")
        print(f"exact_score_name={exact_score.name}")
        print(f"exact_mean={exact_score.mean}")
        print(f"custom_rows={len(custom_result.row_scores)}")
        print(f"custom_score_name={custom_score.name}")
        print(f"custom_mean={custom_score.mean}")
        print(f"multi_job={multi_job.name}")
        print(f"multi_rows={len(multi_result.row_scores)}")
        print(f"multi_scores={_aggregate_score_names(multi_result)}")
        print(f"multi_means={[score.mean for score in multi_result.aggregate_scores.scores]}")
        print(f"remote_job_metric_cases={[metric_case.name for metric_case in metric_cases]}")
        print(f"bundle_only_metric_cases={[metric_case.name for metric_case in bundle_only_metric_cases]}")

        assert len(exact_result.row_scores) == 2
        assert exact_score.name == "exact-match.exact-match"
        assert exact_score.mean == 0.5
        assert len(custom_result.row_scores) == 2
        assert custom_score.name == "custom-contains.contains"
        assert custom_score.mean == 1.0
        assert len(multi_result.row_scores) == 2
        multi_score_names = _aggregate_score_names(multi_result)
        for metric_case in metric_cases:
            _assert_scores_present(multi_score_names, metric_case.expected_aggregate_scores)
        if _live_nvidia_enabled():
            live_llm_cases = [MetricCase("live_llm_judge", _live_llm_judge_metric(), ("llm-judge.correctness",))]
            _run_live_metric_job(
                plugin_resource=plugin_resource,
                bundler=bundler,
                label="live_llm_judge",
                metric_cases=live_llm_cases,
                dataset=dataset[:1],
            )
            _run_live_metric_job(
                plugin_resource=plugin_resource,
                bundler=bundler,
                label="live_ragas_rag",
                metric_cases=_live_rag_metric_cases(),
                dataset=_live_rag_dataset(),
            )
            _run_live_metric_job(
                plugin_resource=plugin_resource,
                bundler=bundler,
                label="live_ragas_agentic",
                metric_cases=_live_agentic_metric_cases(),
                dataset=_live_agentic_dataset(),
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
