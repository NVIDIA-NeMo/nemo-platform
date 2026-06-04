# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM judge metric runtime implementation."""

import logging
from copy import copy, deepcopy
from typing import Any, Literal, Protocol, Self

import nemo_platform.beta.evaluator.inference as inference
from nemo_platform.beta.evaluator.enums import ModelFormat
from nemo_platform.beta.evaluator.inference import InferenceFn, InferenceHookParams
from nemo_platform.beta.evaluator.inference import new_hooks as _new_inference_hooks
from nemo_platform.beta.evaluator.metrics.hooks import HooksBase
from nemo_platform.beta.evaluator.metrics.protocol import (
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nemo_platform.beta.evaluator.metrics.resolution import collect_model_refs, resolve_model_refs
from nemo_platform.beta.evaluator.metrics.template_rendering import (
    TemplateSample,
    build_template_context,
    sample_template_payload,
)
from nemo_platform.beta.evaluator.resolver_protocols import ModelResolver, SecretResolver
from nemo_platform.beta.evaluator.structured_output import InferenceStructuredOutput, detect_structured_output_mode
from nemo_platform.beta.evaluator.templates import render_request
from nemo_platform.beta.evaluator.values.common import SecretRef, SupportedJobTypes
from nemo_platform.beta.evaluator.values.llm_judge_defaults import (
    default_judge_prompt_template_chat,
    default_judge_prompt_template_completions,
    default_judge_prompt_template_for_model,
)
from nemo_platform.beta.evaluator.values.metrics import LLM_JUDGE_SCORES_CONTEXT_KEY, LLMJudge
from nemo_platform.beta.evaluator.values.models import Model, ModelRef
from nemo_platform.beta.evaluator.values.params import InferenceParams, ReasoningParams, RunConfig, RunConfigOnline
from nemo_platform.beta.evaluator.values.results import MetricScore
from nemo_platform.beta.evaluator.values.scores import (
    JSONScoreParser,
    RangeScore,
    RubricScore,
    Score,
    ScoreParser,
    ScoreParserJSON,
    ScoreParserRegex,
)
from openai import AsyncOpenAI
from pydantic import PrivateAttr
from pydantic_core import PydanticUndefined

__all__ = [
    "InferenceParams",
    "LLMJudgeMetric",
    "Model",
    "ModelRef",
    "ReasoningParams",
    "Score",
    "default_judge_prompt_template_chat",
    "default_judge_prompt_template_completions",
    "generate_structured_output",
    "new_hooks",
]

_logger = logging.getLogger(__name__)


class _LLMJudgeHookParams(InferenceHookParams, Protocol):
    model: Model | ModelRef
    scores: list[Score]
    prompt_template: str | dict | None


class LLMJudgeMetric(HooksBase, LLMJudge):
    """Runtime metric implementation for LLM-as-a-judge scoring."""

    _use_max_completion_tokens: bool = False
    _api_key: str | None = None
    _client: AsyncOpenAI | None = PrivateAttr(default=None)
    _inference_fn: InferenceFn | None = None
    _parsers: dict[str, ScoreParser] = PrivateAttr(default_factory=dict)
    _score_dumps: dict[str, dict[str, Any]] = PrivateAttr(default_factory=dict)
    _prompt_template_is_default: bool = PrivateAttr(default=False)
    job_type: Literal[SupportedJobTypes.ONLINE, SupportedJobTypes.OFFLINE] = SupportedJobTypes.ONLINE

    @property
    def client(self) -> AsyncOpenAI:
        """Lazily instantiates the client on first access."""
        if self._client is None:
            self._client = inference.new_inference_client(self._require_model(), api_key=self._api_key)
        return self._client

    def _require_model(self) -> Model:
        """Return the resolved model or fail clearly when a ModelRef remains unresolved."""
        if isinstance(self.model, Model):
            return self.model
        raise ValueError(
            f"Model reference '{self.model.root}' has not been resolved. "
            "Register it with LocalBackend.model_resolver.register_model() before local execution."
        )

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        """
        Override Pydantic __deepcopy__ which returns a deep copy of the model with support to instantiate a new
        AsyncOpenAI client.
        """
        cls = type(self)
        m = cls.__new__(cls)
        object.__setattr__(m, "__dict__", deepcopy(self.__dict__, memo=memo))
        object.__setattr__(m, "__pydantic_extra__", deepcopy(self.__pydantic_extra__, memo=memo))
        # This next line doesn't need a deepcopy because __pydantic_fields_set__ is a set[str],
        # and attempting a deepcopy would be marginally slower.
        object.__setattr__(m, "__pydantic_fields_set__", copy(self.__pydantic_fields_set__))

        if not hasattr(self, "__pydantic_private__") or self.__pydantic_private__ is None:
            object.__setattr__(m, "__pydantic_private__", None)
        else:
            # Runtime auth/client state must be recreated for the copied model.
            private_attrs = deepcopy(
                {
                    k: v
                    for k, v in self.__pydantic_private__.items()
                    if v is not PydanticUndefined and k not in {"_client", "_api_key"}
                },
                memo=memo,
            )
            private_attrs["_client"] = None
            private_attrs["_api_key"] = None
            object.__setattr__(m, "__pydantic_private__", private_attrs)

        return m

    def set_inference_fn(self, inference_fn: InferenceFn) -> None:
        """Set the inference function to use for LLM calls."""
        self._inference_fn = inference_fn

    def apply_evaluation_job_params(self, params: RunConfig) -> None:
        """Apply execution job type before resolving generated prompt defaults."""
        self.job_type = SupportedJobTypes.ONLINE if isinstance(params, RunConfigOnline) else SupportedJobTypes.OFFLINE
        self._ensure_default_prompt_template()

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return outputs emitted by this metric."""
        specs: list[MetricOutputSpec] = []
        for score in self.scores:
            if isinstance(score, RubricScore):
                specs.append(MetricOutputSpec.continuous_score(score.name, description=score.description))
                specs.append(
                    MetricOutputSpec.label(
                        f"{score.name}.label",
                        description=f"Selected rubric label for {score.name}",
                    )
                )
            else:
                specs.append(MetricOutputSpec.continuous_score(score.name, description=score.description))
        return specs

    def _handle_none_output_error(self, response: dict) -> ValueError:
        error_message = "LLM judge returned no usable textual content for score parsing"
        message = response.get("choices", [{}])[0].get("message")
        if isinstance(message, dict):
            has_reasoning = any(
                isinstance(value, str) and bool(value.strip())
                for value in (message.get("reasoning"), message.get("reasoning_content"))
            )
            if has_reasoning:
                error_message = (
                    f"{error_message}. The response contains reasoning output but no final text content; "
                    "the `max_tokens` budget may have been used entirely by reasoning. "
                    "Try increasing inference `max_tokens` "
                    "or configuring `inference.extra_body.nvext.max_thinking_tokens` for NIM endpoints"
                )
        return ValueError(f"{error_message}. Response: {response}.")

    def _validate_output_text(self, output_text: str | None, response: dict) -> str:
        """Ensure the judge returned textual content that can be parsed."""
        if isinstance(output_text, str):
            return output_text
        raise self._handle_none_output_error(response)

    def _handle_invalid_output(self, error: Exception, fallback: MetricResult, message: str) -> MetricResult:
        if self.ignore_request_failure:
            _logger.warning("%s: %s", message, str(error))
            return fallback
        raise error

    def _nan_result(self) -> MetricResult:
        outputs: list[MetricOutput] = []
        for score in self.scores:
            outputs.append(MetricOutput(name=score.name, value=float("nan")))
            if isinstance(score, RubricScore):
                outputs.append(MetricOutput(name=f"{score.name}.label", value=""))
        return MetricResult(outputs=outputs)

    async def resolve_models(self, model_resolver: ModelResolver) -> None:
        """Resolve judge model references before the metric is used for evaluation."""
        await resolve_model_refs(self, model_resolver)
        self._client = None
        self._api_key = None
        self._ensure_default_prompt_template()
        preprocess_hooks, postprocess_hooks = new_hooks(self)
        self.with_hooks(preprocess=preprocess_hooks, postprocess=postprocess_hooks)

    def model_refs(self) -> dict[str, ModelRef]:
        """Return judge model references present on this metric."""
        return collect_model_refs(self)

    async def resolve_secrets(self, secret_resolver: SecretResolver) -> None:
        """Resolve API key secret if configured and reinitialize AsyncOpenAI client. Must be called before using the metric."""
        model = self._require_model()
        if model.api_key_secret:
            secret_name = model.api_key_secret.root
            self._api_key = await secret_resolver.resolve_secret(model.api_key_secret)
            if not self._api_key:
                raise ValueError(f"Missing secret '{secret_name}' for API key authentication with LLM judge.")
            self._client = inference.new_inference_client(model, api_key=self._api_key)

    async def preflight(self) -> None:
        """Resolve structured-output mode once before parallel inference starts."""
        model = self._require_model()
        if model.format != ModelFormat.NVIDIA_NIM or not self.structured_output:
            return

        structured_hook: InferenceStructuredOutput | None = None
        for hook in self._preprocess_hooks:
            if isinstance(hook, InferenceStructuredOutput):
                structured_hook = hook
                break

        if structured_hook is None:
            return

        mode = await detect_structured_output_mode(
            format=model.format,
            model=model,
            inference_fn=self.inference_fn,
            api_key=self._api_key,
            probe_schema={
                "type": "object",
                "properties": {"__nmp_probe_score": {"type": "integer"}},
                "required": ["__nmp_probe_score"],
                "additionalProperties": False,
            },
        )
        structured_hook.set_mode(mode)
        _logger.info("NIM structured output mode selected: %s", mode.value)

    def secrets(self) -> dict[str, SecretRef]:
        """Return secret env mappings required by this metric."""
        if isinstance(self.model, ModelRef):
            return {}
        if self.model.api_key_secret and self.model.api_key_env:
            return {self.model.api_key_env: self.model.api_key_secret}
        return {}

    @property
    def inference_fn(self) -> InferenceFn:
        """Get the inference function, defaulting to the global one if not injected."""
        return self._inference_fn or inference.make_inference_request

    def model_post_init(self, context: Any, /) -> None:
        # Pydantic runs model_post_init() during BaseModel construction, before any
        # custom __init__ logic would execute. Derive structured_output here so the
        # first parser initialization validates against the finalized JSON schema.
        self._prompt_template_is_default = self.prompt_template is None
        self.structured_output = generate_structured_output(self)
        self._initialize_score_parsers()
        preprocess_hooks, postprocess_hooks = new_hooks(self)
        self.with_hooks(preprocess=preprocess_hooks, postprocess=postprocess_hooks)
        return super().model_post_init(context)

    def _ensure_default_prompt_template(self) -> None:
        """Set the default prompt template for the configured judge model."""
        if not self._prompt_template_is_default:
            return
        if isinstance(self.model, ModelRef):
            return
        self.prompt_template = default_judge_prompt_template_for_model(self.model, self.job_type)

    def _initialize_score_parsers(self) -> None:
        if not self.scores:
            return

        for score in self.scores:
            if not score.parser:
                raise ValueError(f"parser is required for LLM-as-a-Judge score {score.name}: {score}")

            parser_type = score.parser.type
            if parser_type == ScoreParserJSON.parser_type:
                parser = ScoreParserJSON(score=score, structured_output=self.structured_output)
            elif parser_type == ScoreParserRegex.parser_type:
                parser = ScoreParserRegex(score=score)
            else:
                raise ValueError(f"unknown parser type for LLM-as-a-Judge score {score.name}: {parser_type}")

            self._parsers[score.name] = parser
            self._score_dumps[score.name] = score.model_dump(mode="json", exclude={"parser"})

    def _render_request(self, item: dict, sample: TemplateSample) -> dict:
        sample_payload = sample_template_payload(sample)
        overlapping_keys = set(item.keys()) & set(sample_payload.keys())
        if overlapping_keys:
            _logger.warning(
                "Dataset columns %s overlap with model response keys. "
                "Model response values will be used. "
                "To access your dataset values, use 'item.<column_name>' in your template.",
                overlapping_keys,
            )

        context = build_template_context(item, sample)
        if self._score_dumps:
            context[LLM_JUDGE_SCORES_CONTEXT_KEY] = self._score_dumps
        self._ensure_default_prompt_template()
        if self.prompt_template is None:
            model_ref = self.model.root if isinstance(self.model, ModelRef) else "<unknown>"
            raise ValueError(
                f"Model reference '{model_ref}' has not been resolved. "
                "Register it with LocalBackend.model_resolver.register_model() before local execution."
            )
        request = render_request(self.prompt_template, context=context)

        if "max_tokens" not in request:
            request["max_tokens"] = 1024
        if self._use_max_completion_tokens:
            request["max_completion_tokens"] = request["max_tokens"]
            del request["max_tokens"]

        return self._apply_preprocess_hooks(request)

    def _retry_with_max_completion_tokens(self, request: dict) -> dict:
        if not self._use_max_completion_tokens:
            _logger.warning(
                "Model does not support 'max_tokens' parameter. Switching to 'max_completion_tokens' for all future requests."
            )
            self._use_max_completion_tokens = True
        request["max_completion_tokens"] = request["max_tokens"]
        del request["max_tokens"]
        return request

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute structured score output for one item/sample pair."""
        item = input.row.data
        sample = input.candidate
        request = self._render_request(item, sample)

        try:
            response = await self.inference_fn(self._require_model(), request, 3, client=self.client)
        except inference.ClientInferenceError as error:
            if "max_tokens" in request and "'max_tokens' is not supported with this model" in error.args[0]:
                request = self._retry_with_max_completion_tokens(request)
                response = await self.inference_fn(self._require_model(), request, 3, client=self.client)
            else:
                return self._handle_invalid_output(
                    error,
                    self._nan_result(),
                    "Inference failed with LLM judge, marking as NaN",
                )

        try:
            output_text = self._validate_output_text(
                inference.process_output(response, hooks=self._postprocess_hooks),
                response,
            )
        except ValueError as error:
            return self._handle_invalid_output(
                error,
                self._nan_result(),
                "LLM judge returned invalid output, marking as NaN",
            )

        result = MetricResult(outputs=[])
        for score_name, parser in self._parsers.items():
            score = parser.parse(output_text)
            _logger.debug("Parsed score %s: %s", score_name, score.value)
            result.outputs.append(MetricOutput(name=score.name, value=score.value))
            label = _selected_rubric_label(score)
            if label is not None:
                result.outputs.append(MetricOutput(name=f"{score.name}.label", value=label))
        return result


def _selected_rubric_label(score: MetricScore) -> str | None:
    """Return the selected rubric label recorded by the parser, if any."""
    if not score.stats or not score.stats.rubric_distribution:
        return None
    for rubric_stat in score.stats.rubric_distribution:
        if rubric_stat.count:
            return rubric_stat.label
    return ""


def new_hooks(params: _LLMJudgeHookParams | None):
    """Initialize preprocess and postprocess hooks for the LLM judge."""
    model_format = params.model.format if params and isinstance(params.model, Model) else ModelFormat.NVIDIA_NIM
    return _new_inference_hooks(params, model_format=model_format)


def generate_structured_output(params: _LLMJudgeHookParams) -> dict | None:
    """Derive JSON schema for LLM structured output from score criteria."""
    if params.structured_output:
        return params.structured_output

    properties: dict[str, dict[str, Any]] = {}
    for score in params.scores:
        if not isinstance(score.parser, JSONScoreParser):
            continue

        key = score.parser.json_path
        if isinstance(score, RubricScore):
            schema = {
                "type": "string",
                "enum": [rubric.label for rubric in score.rubric],
            }
        elif isinstance(score, RangeScore):
            schema = {
                "type": "integer" if isinstance(score.minimum, int) else "number",
                "minimum": score.minimum,
                "maximum": score.maximum,
            }
        else:
            continue

        existing = properties.get(key)
        if existing is not None and existing != schema:
            raise ValueError(
                f"conflicting auto-generated structured_output for json_path '{key}'; "
                "provide explicit structured_output"
            )
        properties[key] = schema

    if not properties:
        return None

    return {
        "schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys()),
        }
    }
