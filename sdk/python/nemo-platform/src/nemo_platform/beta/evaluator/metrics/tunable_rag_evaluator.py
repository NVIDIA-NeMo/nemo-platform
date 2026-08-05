# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tunable RAG evaluator metric runtime implementation.

Ported from https://github.com/NVIDIA/NeMo-Agent-Toolkit/blob/main/packages/nvidia_nat_langchain/src/nat/plugins/langchain/eval/tunable_rag_evaluator.py
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

import nemo_platform.beta.evaluator.inference as inference
from nemo_platform.beta.evaluator.inference import InferenceFn
from nemo_platform.beta.evaluator.metrics.hooks import HooksBase
from nemo_platform.beta.evaluator.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_platform.beta.evaluator.metrics.resolution import collect_model_refs, resolve_model_refs
from nemo_platform.beta.evaluator.metrics.tunable_rag_defaults import (
    CUSTOM_SCORING_JSON_SCHEMA,
    DEFAULT_SCORING_JSON_SCHEMA,
    build_evaluation_prompt,
    normalize_score_weights,
)
from nemo_platform.beta.evaluator.resolver_protocols import ModelResolver, SecretResolver
from nemo_platform.beta.evaluator.values.common import SecretRef, SupportedJobTypes
from nemo_platform.beta.evaluator.values.metrics import TunableRagEvaluator
from nemo_platform.beta.evaluator.values.models import Model, ModelRef
from nemo_platform.beta.evaluator.values.params import RunConfig, RunConfigOnline
from openai import AsyncOpenAI
from pydantic import PrivateAttr

__all__ = ["TunableRagEvaluatorMetric"]

_logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class TunableRagEvaluatorMetric(HooksBase, TunableRagEvaluator):
    """LLM-judge metric with weighted coverage/correctness/relevance composite scoring."""

    _api_key: str | None = None
    _client: AsyncOpenAI | None = PrivateAttr(default=None)
    _inference_fn: InferenceFn | None = None
    # Populated from RunConfigOnline.max_retries via apply_evaluation_job_params.
    _max_retries: int = PrivateAttr(default=3)
    job_type: Literal[SupportedJobTypes.ONLINE, SupportedJobTypes.OFFLINE] = SupportedJobTypes.ONLINE

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = inference.new_inference_client(self._require_model(), api_key=self._api_key)
        return self._client

    def _require_model(self) -> Model:
        if isinstance(self.model, Model):
            return self.model
        raise ValueError(
            f"Model reference '{self.model.root}' has not been resolved. "
            "Register it with LocalBackend.model_resolver.register_model() before local execution."
        )

    @property
    def inference_fn(self) -> InferenceFn:
        return self._inference_fn or inference.make_inference_request

    def apply_evaluation_job_params(self, params: RunConfig) -> None:
        """Apply online job params; ``max_retries`` lives on ``RunConfigOnline``, not InferenceParams."""
        self.job_type = SupportedJobTypes.ONLINE if isinstance(params, RunConfigOnline) else SupportedJobTypes.OFFLINE
        if isinstance(params, RunConfigOnline):
            self._max_retries = params.max_retries

    def model_refs(self) -> dict[str, ModelRef]:
        return collect_model_refs(self)

    def secrets(self) -> dict[str, SecretRef]:
        if isinstance(self.model, ModelRef):
            return {}
        if self.model.api_key_secret and self.model.api_key_env:
            return {self.model.api_key_env: self.model.api_key_secret}
        return {}

    async def resolve_secrets(self, secret_resolver: SecretResolver) -> None:
        model = self._require_model()
        if model.api_key_secret:
            secret_name = model.api_key_secret.root
            self._api_key = await secret_resolver.resolve_secret(model.api_key_secret)
            if not self._api_key:
                raise ValueError(f"Missing secret '{secret_name}' for tunable RAG judge authentication.")
            self._client = inference.new_inference_client(model, api_key=self._api_key)

    async def resolve_models(self, model_resolver: ModelResolver) -> None:
        await resolve_model_refs(self, model_resolver)

    def output_spec(self) -> list[MetricOutputSpec]:
        if self.default_scoring:
            return [
                MetricOutputSpec.continuous_score("average_score"),
                MetricOutputSpec.continuous_score("coverage_score"),
                MetricOutputSpec.continuous_score("correctness_score"),
                MetricOutputSpec.continuous_score("relevance_score"),
                MetricOutputSpec.label("reasoning"),
            ]
        return [
            MetricOutputSpec.continuous_score("average_score"),
            MetricOutputSpec.label("reasoning"),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        instruction, answer_description, generated_answer = _extract_eval_fields(input)
        request = self._build_request(instruction, answer_description, generated_answer)
        max_retries = self._max_retries

        try:
            response = await self.inference_fn(self._require_model(), request, max_retries, client=self.client)
            output_text = inference.process_output(response, hooks=self._postprocess_hooks)
        except inference.ClientInferenceError as error:
            return self._failed_result(f"Inference failed: {error}")

        if not isinstance(output_text, str) or not output_text.strip():
            return self._failed_result("Judge returned empty output.")

        parsed = _parse_json_object(output_text)
        if parsed is None:
            return self._failed_result("Error in evaluator from parsing judge LLM response.")

        return self._score_from_parsed(parsed)

    def _build_request(self, instruction: str, answer_description: str, generated_answer: str) -> dict[str, Any]:
        prompt = build_evaluation_prompt(
            judge_llm_prompt=self.judge_llm_prompt,
            instruction=instruction,
            answer_description=answer_description,
            generated_answer=generated_answer,
            default_scoring=self.default_scoring,
        )
        schema = DEFAULT_SCORING_JSON_SCHEMA if self.default_scoring else CUSTOM_SCORING_JSON_SCHEMA
        request: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": "You must respond only in JSON format."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "tunable_rag_evaluator",
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        if self.inference is not None:
            request.update(self.inference.model_dump(exclude_none=True))
        return self._apply_preprocess_hooks(request)

    def _score_from_parsed(self, parsed: dict[str, Any]) -> MetricResult:
        if self.default_scoring:
            try:
                coverage = float(parsed["coverage_score"])
                correctness = float(parsed["correctness_score"])
                relevance = float(parsed["relevance_score"])
                reasoning = str(parsed["reasoning"])
            except (KeyError, TypeError, ValueError):
                return self._failed_result("Missing or invalid keys in default scoring judge response.")

            coverage_w, correctness_w, relevance_w = normalize_score_weights(self.default_score_weights)
            average = coverage_w * coverage + correctness_w * correctness + relevance_w * relevance
            return MetricResult(
                outputs=[
                    MetricOutput(name="average_score", value=average),
                    MetricOutput(name="coverage_score", value=coverage),
                    MetricOutput(name="correctness_score", value=correctness),
                    MetricOutput(name="relevance_score", value=relevance),
                    MetricOutput(name="reasoning", value=reasoning),
                ]
            )

        try:
            average = float(parsed["score"])
            reasoning = str(parsed["reasoning"])
        except (KeyError, TypeError, ValueError):
            return self._failed_result("Missing or invalid keys in custom scoring judge response.")
        return MetricResult(
            outputs=[
                MetricOutput(name="average_score", value=average),
                MetricOutput(name="reasoning", value=reasoning),
            ]
        )

    def _failed_result(self, reasoning: str) -> MetricResult:
        if self.default_scoring:
            return MetricResult(
                outputs=[
                    MetricOutput(name="average_score", value=0.0),
                    MetricOutput(name="coverage_score", value=0.0),
                    MetricOutput(name="correctness_score", value=0.0),
                    MetricOutput(name="relevance_score", value=0.0),
                    MetricOutput(name="reasoning", value=reasoning),
                ]
            )
        return MetricResult(
            outputs=[
                MetricOutput(name="average_score", value=0.0),
                MetricOutput(name="reasoning", value=reasoning),
            ]
        )


def _extract_eval_fields(metric_input: MetricInput) -> tuple[str, str, str]:
    """Pull Fabric agent-eval fields: ``inputs.instruction`` + ``reference.answer``."""
    row = metric_input.row.data
    inputs = row.get("inputs")
    if not isinstance(inputs, dict):
        inputs = row
    instruction = str(inputs.get("instruction") or "")
    reference = row.get("reference") or {}
    if isinstance(reference, dict):
        answer_description = str(reference.get("answer") or reference.get("expected") or "")
    else:
        answer_description = str(reference)
    generated_answer = str(metric_input.candidate.output_text or metric_input.candidate.response or "")
    return instruction, answer_description, generated_answer


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fence_match = _JSON_FENCE_RE.search(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
