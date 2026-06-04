# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Protocol, cast, runtime_checkable

from nemo_evaluator_sdk import (
    BLEUMetric,
    ExactMatchMetric,
    F1Metric,
    LLMJudgeMetric,
    Model,
    NumberCheckMetric,
    ROUGEMetric,
    StringCheckMetric,
    ToolCallingMetric,
)
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.inference import InferenceFn
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithPreflight, MetricWithSecrets, SecretResolver
from nemo_evaluator_sdk.metrics.ragas.metrics import RAGAS_METRIC_CLASSES
from nemo_evaluator_sdk.values import MetricBase, SupportedJobTypes
from nmp.evaluator.app import inference as app_inference
from nmp.evaluator.app.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric
from nmp.evaluator.app.values.metrics import Metric as MetricParams

# Map of Metric enum values to class.
# Keep this registry explicit
_METRIC_CLASSES: dict[MetricType, type[MetricBase]] = {
    MetricType.BLEU: BLEUMetric,
    MetricType.EXACT_MATCH: ExactMatchMetric,
    MetricType.F1: F1Metric,
    MetricType.LLM_JUDGE: LLMJudgeMetric,
    MetricType.NUMBER_CHECK: NumberCheckMetric,
    MetricType.REMOTE: RemoteMetric,
    MetricType.NEMO_AGENT_TOOLKIT_REMOTE: NemoAgentToolkitRemoteMetric,
    MetricType.ROUGE: ROUGEMetric,
    MetricType.STRING_CHECK: StringCheckMetric,
    MetricType.TOOL_CALLING: ToolCallingMetric,
}

# Combined map including RAGAS metrics (for type checking purposes)
_ALL_METRIC_CLASSES: dict[MetricType, type[MetricBase]] = {
    **_METRIC_CLASSES,
    **cast(dict[MetricType, type[MetricBase]], RAGAS_METRIC_CLASSES),
}


@runtime_checkable
class MetricWithInference(Protocol):
    """Protocol for metrics that require an inference function (e.g., LLM Judge)."""

    def set_inference_fn(self, inference_fn: InferenceFn) -> None:
        """
        Set the inference function to use for LLM calls.
        Called before the metric is used for evaluation.
        """
        ...


def metric_runtime_kwargs(metric_params: MetricParams, metric_cls: type[MetricBase]) -> dict[str, object]:
    """Project a service metric config down to the runtime metric constructor.

    Service value/entity models may contain persistence-only fields like
    `name`, `workspace`, `id`, or timestamps. Direct SDK runtime metrics only
    accept their declared runtime/config fields, so filter the dumped config to
    the target runtime model schema before construction.

    Args:
        metric_params: The metric parameters object from nmp.evaluator.app.values.metrics.
        metric_cls: The SDK runtime metric class from nmp.nemo_evaluator_sdk.metrics.

    Returns:
        A dictionary of runtime keyword arguments.
    """

    config_dict = metric_params.model_dump(mode="python", exclude_none=True)
    runtime_kwargs = {
        field_name: value for field_name, value in config_dict.items() if field_name in metric_cls.model_fields
    }

    if metric_params.type == MetricType.LLM_JUDGE and "prompt_template" not in metric_params.model_fields_set:
        runtime_kwargs.pop("prompt_template", None)

    return runtime_kwargs


async def new_metric(
    metric_params: MetricParams,
    job_type: SupportedJobTypes = SupportedJobTypes.ONLINE,
    secret_resolver: SecretResolver | None = None,
    *,
    inference_fn: InferenceFn | None = None,
    run_preflight: bool = False,
) -> Metric:
    """Create a new metric instance.

    All metrics are initialized the same way. If a metric implements
    MetricWithSecrets and a secret_resolver is provided, resolve_secrets
    is called after construction.

    Args:
        metric_config: The metric configuration.
        job_type: The job type (online or offline).
        secret_resolver: Async function to resolve secret names to values.
            For jobs running in containers, pass None to skip resolution
            (secrets are injected as environment variables at runtime).
            For API calls, this fetches from the secrets service.
            Defaults to reading from environment variables.
        inference_fn: Optional function to make inference requests. If provided,
            it will be used by metrics that require LLM inference (e.g., LLMJudgeMetric).
            Defaults to the global inference.make_inference_request.
        run_preflight: Whether to run one-time metric preflight after setup.
            Intended for execution paths (not compilation/setup-only paths).
    """
    metric_cls = _ALL_METRIC_CLASSES.get(metric_params.type)
    if not metric_cls:
        raise ValueError(f"Unknown metric type: {metric_params.type}")

    # Most service metrics now instantiate the SDK runtime models directly from
    # field-based config data. The remaining exception is BaseRAGASMetric,
    # whose runtime base still exposes the older `params=...` constructor, so
    # keep this compatibility branch until those metrics are migrated to the
    # direct runtime-class pattern as well.
    metric_kwargs = metric_runtime_kwargs(metric_params, metric_cls)
    if "job_type" in metric_cls.model_fields:
        metric_kwargs["job_type"] = job_type
    metric_model = metric_cls(**metric_kwargs)

    metric = cast(Metric, metric_model)

    if isinstance(metric, LLMJudgeMetric) and isinstance(metric.model, Model):
        custom_headers = app_inference.get_platform_headers(metric.model.url)
        metric.model = metric.model.with_default_headers(headers=custom_headers)

    if secret_resolver is not None and isinstance(metric, MetricWithSecrets):
        await metric.resolve_secrets(secret_resolver)
    if inference_fn is not None and isinstance(metric, MetricWithInference):
        metric.set_inference_fn(inference_fn)
    if run_preflight and isinstance(metric, MetricWithPreflight):
        await metric.preflight()

    return metric
