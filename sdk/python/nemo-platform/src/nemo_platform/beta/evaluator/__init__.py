# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Evaluator SDK.

The public surface resolves lazily (PEP 562). Importing this package must not drag in the
execution/backend or metric stack: importing any submodule runs this module first, so eager
re-exports made ``import nemo_platform.beta.evaluator.agent_eval.runtimes.harbor_runtime`` — all the
optimizer needs — cost ~1400 modules (openai, sacrebleu, zstandard, pyarrow, ...) instead
of ~480, and turned every one of those transitive packages into an evaluation-time failure mode
for the SDK-backed evaluator.

Add a new re-export to ``_LAZY_ATTRS``, the ``TYPE_CHECKING`` block and ``__all__`` — never as a
module-level import. ``tests/test_lazy_public_api.py`` locks the boundary in.
"""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Annotations and static analysis only; these must never execute at run time. Listing the
    # names in ``__all__`` is what marks them as re-exports for ruff and the type checkers.
    from nemo_platform.beta.evaluator.agent_stream_translation import (
        AgentStreamTranslation,
        AgentStreamTranslationContext,
        AgentStreamTranslator,
        SseFrame,
    )
    from nemo_platform.beta.evaluator.datasets import DatasetLoadError, load_dataset, load_dataset_as_dicts
    from nemo_platform.beta.evaluator.execution.backends.local.backend import LocalBackend
    from nemo_platform.beta.evaluator.execution.evaluator import Evaluator
    from nemo_platform.beta.evaluator.execution.values import (
        EvaluationError,
        EvaluationPhase,
    )
    from nemo_platform.beta.evaluator.metrics.bleu import BLEUMetric
    from nemo_platform.beta.evaluator.metrics.exact_match import ExactMatchMetric
    from nemo_platform.beta.evaluator.metrics.f1 import F1Metric
    from nemo_platform.beta.evaluator.metrics.llm_judge import LLMJudgeMetric
    from nemo_platform.beta.evaluator.metrics.number_check import NumberCheckMetric
    from nemo_platform.beta.evaluator.metrics.protocol import (
        Metric,
        MetricTypeName,
        validate_metric_result,
    )
    from nemo_platform.beta.evaluator.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric
    from nemo_platform.beta.evaluator.metrics.rouge import ROUGEMetric
    from nemo_platform.beta.evaluator.metrics.string_check import StringCheckMetric
    from nemo_platform.beta.evaluator.metrics.tool_calling import ToolCallingMetric
    from nemo_platform.beta.evaluator.metrics.tunable_rag_evaluator import TunableRagEvaluatorMetric
    from nemo_platform.beta.evaluator.resolver_protocols import ModelResolver, SecretResolver
    from nemo_platform.beta.evaluator.resolvers import LocalModelResolver, LocalSecretResolver
    from nemo_platform.beta.evaluator.structured_output import (
        InferenceFn,
        InferenceStructuredOutput,
        StructuredOutput,
        StructuredOutputMode,
        default_structured_output_mode,
        detect_structured_output_mode,
    )
    from nemo_platform.beta.evaluator.values import (
        Agent,
        AgentBase,
        BooleanValue,
        CandidateOutput,
        ContinuousScore,
        DatasetRow,
        DatasetRows,
        DiscreteScore,
        EvaluationResult,
        FieldMapping,
        InferenceParams,
        JSONScoreParser,
        Label,
        MetricDescriptor,
        MetricDiagnostic,
        MetricInput,
        MetricOutput,
        MetricOutputSpec,
        MetricResult,
        Model,
        ModelRef,
        GenericAgent,
        NatAgentConfig,
        NemoAgentToolkitAgent,
        RangeScore,
        ReasoningParams,
        RemoteScore,
        RubricScore,
        RunConfig,
        RunConfigOnline,
        RunConfigOnlineModel,
        SecretRef,
    )

try:
    version = _package_version("nemo-evaluator-sdk")
except PackageNotFoundError:
    version = "0.0.0"

# Re-exported name -> the submodule that defines it, relative to this package. Relative on
# purpose: the vendoring tool mirrors this file into nemo_platform.beta.evaluator by rewriting
# module paths, and a relative name has nothing to rewrite, so the mirror is correct by
# construction. Mirrors the TYPE_CHECKING block above, in the same order.
_LAZY_ATTRS: dict[str, str] = {
    "AgentStreamTranslation": ".agent_stream_translation",
    "AgentStreamTranslationContext": ".agent_stream_translation",
    "AgentStreamTranslator": ".agent_stream_translation",
    "SseFrame": ".agent_stream_translation",
    "DatasetLoadError": ".datasets",
    "load_dataset": ".datasets",
    "load_dataset_as_dicts": ".datasets",
    "LocalBackend": ".execution.backends.local.backend",
    "Evaluator": ".execution.evaluator",
    "EvaluationError": ".execution.values",
    "EvaluationPhase": ".execution.values",
    "BLEUMetric": ".metrics.bleu",
    "ExactMatchMetric": ".metrics.exact_match",
    "F1Metric": ".metrics.f1",
    "LLMJudgeMetric": ".metrics.llm_judge",
    "NumberCheckMetric": ".metrics.number_check",
    "Metric": ".metrics.protocol",
    "MetricTypeName": ".metrics.protocol",
    "validate_metric_result": ".metrics.protocol",
    "NemoAgentToolkitRemoteMetric": ".metrics.remote",
    "RemoteMetric": ".metrics.remote",
    "ROUGEMetric": ".metrics.rouge",
    "StringCheckMetric": ".metrics.string_check",
    "ToolCallingMetric": ".metrics.tool_calling",
    "TunableRagEvaluatorMetric": ".metrics.tunable_rag_evaluator",
    "ModelResolver": ".resolver_protocols",
    "SecretResolver": ".resolver_protocols",
    "LocalModelResolver": ".resolvers",
    "LocalSecretResolver": ".resolvers",
    "InferenceFn": ".structured_output",
    "InferenceStructuredOutput": ".structured_output",
    "StructuredOutput": ".structured_output",
    "StructuredOutputMode": ".structured_output",
    "default_structured_output_mode": ".structured_output",
    "detect_structured_output_mode": ".structured_output",
    "Agent": ".values",
    "AgentBase": ".values",
    "BooleanValue": ".values",
    "CandidateOutput": ".values",
    "ContinuousScore": ".values",
    "DatasetRow": ".values",
    "DatasetRows": ".values",
    "DiscreteScore": ".values",
    "EvaluationResult": ".values",
    "FieldMapping": ".values",
    "InferenceParams": ".values",
    "JSONScoreParser": ".values",
    "Label": ".values",
    "MetricDescriptor": ".values",
    "MetricDiagnostic": ".values",
    "MetricInput": ".values",
    "MetricOutput": ".values",
    "MetricOutputSpec": ".values",
    "MetricResult": ".values",
    "Model": ".values",
    "ModelRef": ".values",
    "GenericAgent": ".values",
    "NatAgentConfig": ".values",
    "NemoAgentToolkitAgent": ".values",
    "RangeScore": ".values",
    "ReasoningParams": ".values",
    "RemoteScore": ".values",
    "RubricScore": ".values",
    "RunConfig": ".values",
    "RunConfigOnline": ".values",
    "RunConfigOnlineModel": ".values",
    "SecretRef": ".values",
}

__all__ = [
    "BLEUMetric",
    "Agent",
    "AgentBase",
    "EvaluationError",
    "EvaluationPhase",
    "DatasetLoadError",
    "DatasetRows",
    "RunConfig",
    "RunConfigOnline",
    "RunConfigOnlineModel",
    "EvaluationResult",
    "Evaluator",
    "ExactMatchMetric",
    "F1Metric",
    "FieldMapping",
    "InferenceParams",
    "InferenceFn",
    "InferenceStructuredOutput",
    "JSONScoreParser",
    "Metric",
    "MetricTypeName",
    "MetricDescriptor",
    "MetricDiagnostic",
    "MetricInput",
    "MetricOutput",
    "MetricOutputSpec",
    "MetricResult",
    "LLMJudgeMetric",
    "BooleanValue",
    "CandidateOutput",
    "ContinuousScore",
    "DatasetRow",
    "DiscreteScore",
    "Label",
    "LocalBackend",
    "LocalModelResolver",
    "LocalSecretResolver",
    "Model",
    "ModelRef",
    "GenericAgent",
    "ModelResolver",
    "NatAgentConfig",
    "NemoAgentToolkitAgent",
    "AgentStreamTranslation",
    "AgentStreamTranslationContext",
    "AgentStreamTranslator",
    "NemoAgentToolkitRemoteMetric",
    "NumberCheckMetric",
    "RangeScore",
    "ReasoningParams",
    "RemoteMetric",
    "RemoteScore",
    "ROUGEMetric",
    "RubricScore",
    "SecretRef",
    "SecretResolver",
    "SseFrame",
    "StringCheckMetric",
    "StructuredOutput",
    "StructuredOutputMode",
    "ToolCallingMetric",
    "TunableRagEvaluatorMetric",
    "default_structured_output_mode",
    "detect_structured_output_mode",
    "load_dataset",
    "load_dataset_as_dicts",
    "validate_metric_result",
    "version",
]


def __getattr__(name: str) -> object:
    """Import the submodule that defines ``name`` on first access (PEP 562).

    ``AttributeError`` is the required failure mode, not ``ImportError``: ``from pkg import sub``
    only falls back to importing a submodule when attribute lookup raises ``AttributeError``, and
    ``hasattr`` checks against this package depend on it too.
    """
    submodule = _LAZY_ATTRS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(submodule, __name__), name)
    globals()[name] = value  # cache, so later lookups skip __getattr__ entirely
    return value


def __dir__() -> list[str]:
    # The declared surface plus any submodule the caller has already imported. ``import_module``
    # and ``TYPE_CHECKING`` are machinery for __getattr__, not API, so keep them out of
    # autocomplete and inspect.getmembers.
    public = {name for name in globals() if not name.startswith("_")} - {"TYPE_CHECKING", "import_module"}
    return sorted(set(__all__) | public)
