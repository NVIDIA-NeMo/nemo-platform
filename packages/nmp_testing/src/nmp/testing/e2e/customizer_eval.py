# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic (no-LLM-judge) base-vs-tuned uplift eval for customizer e2e tests.

Ports the uplift logic from
``plugins/nemo-customizer/.../references/eval_helpers.py`` (which lives under a
hyphenated, non-importable skill path) into an importable helper, and generalizes
it: eval any deployed model — a base entity, a full-weight / DPO output entity, or
a LoRA adapter — over the same CHAT validation rows, then compare scores.

Routing: every target is addressed through the **provider gateway by deployment
name** (matching ``run_inference_test`` in :mod:`nmp.testing.e2e.customizer`):
``/apis/inference-gateway/v2/workspaces/{ws}/provider/{deployment}/-/v1``. The
``model`` field selects what the provider serves — ``{ws}/{entity}`` for a base or
full-weight model, ``{ws}--{adapter}`` for a hot-reloaded LoRA adapter.

Metrics are deterministic (``temperature=0``): F1 / exact-match for SFT (SQuAD gold
spans), F1 / ROUGE for the DPO overlap proxy (generation vs the preferred response).
Each call runs a **single** metric so the result is a flat ``EvaluationResult`` and
we read ``aggregate_scores.scores[0].mean`` — no per-metric key guessing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Train/eval contract: infer on every turn except the final assistant label,
# score the generation against that final turn.
CHAT_USER_PROMPT_TEMPLATE: dict[str, Any] = {"messages": "{{ item.messages[:-1] }}"}
CHAT_REFERENCE_TEMPLATE = "{{ item.messages[-1].content }}"

# Deterministic-metric identifiers accepted by score_rows().
MetricKind = str  # "f1" | "exact_match" | "rouge"


def assert_chat_row(row: dict[str, Any], index: int | None = None) -> None:
    """Validate a row is CHAT-shaped: messages[0]=user-or-system, messages[-1]=assistant."""
    label = f"row {index}" if index is not None else "row"
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError(f"{label}: expected a 'messages' list with a prompt turn + final assistant label")
    if messages[-1].get("role") != "assistant":
        raise ValueError(f"{label}: expected final messages[-1] role='assistant' (the label to score)")


def load_chat_jsonl(path: str) -> list[dict[str, Any]]:
    """Load and validate CHAT ``messages`` rows from a JSONL file."""
    import json
    from pathlib import Path

    rows: list[dict[str, Any]] = []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        assert_chat_row(row, index=index)
        rows.append(row)
    return rows


def provider_route_url(base_url: str, workspace: str, deployment_name: str) -> str:
    """OpenAI-compatible provider-gateway base URL for a deployment."""
    return f"{base_url.rstrip('/')}/apis/inference-gateway/v2/workspaces/{workspace}/provider/{deployment_name}/-/v1"


def base_model_field(workspace: str, entity: str) -> str:
    """``model`` request field for a base or full-weight entity."""
    return f"{workspace}/{entity}"


def lora_model_field(workspace: str, adapter: str) -> str:
    """``model`` request field for a hot-reloaded LoRA adapter."""
    return f"{workspace}--{adapter}"


def _build_target(base_url: str, workspace: str, deployment_name: str, model_field: str):
    """Construct an evaluator ``Model`` target on the provider gateway."""
    from nemo_evaluator_sdk.enums import ModelFormat
    from nemo_evaluator_sdk.values.models import Model

    return Model(
        url=provider_route_url(base_url, workspace, deployment_name),
        name=model_field,
        format=ModelFormat.NVIDIA_NIM,
    )


def _build_config(max_tokens: int, parallelism: int, limit_samples: int | None, enable_thinking: bool):
    """RunConfigOnlineModel with deterministic decoding (temperature=0).

    ``enable_thinking=False`` disables Qwen3-style reasoning traces via
    ``chat_template_kwargs`` so the raw answer is scored, not ``<think>`` output.
    """
    from nemo_evaluator_sdk.values import InferenceParams, RunConfigOnlineModel

    inference_kwargs: dict[str, Any] = {"max_tokens": max_tokens, "temperature": 0}
    if not enable_thinking:
        inference_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return RunConfigOnlineModel(
        parallelism=parallelism,
        limit_samples=limit_samples,
        inference=InferenceParams(**inference_kwargs),
    )


def _metric(kind: MetricKind):
    """Instantiate a deterministic metric keyed on the final assistant turn."""
    if kind == "f1":
        from nemo_evaluator_sdk.metrics.f1 import F1Metric

        return F1Metric(reference=CHAT_REFERENCE_TEMPLATE)
    if kind == "exact_match":
        from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric

        return ExactMatchMetric(reference=CHAT_REFERENCE_TEMPLATE)
    if kind == "rouge":
        from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric

        return ROUGEMetric(reference=CHAT_REFERENCE_TEMPLATE)
    raise ValueError(f"Unknown metric kind: {kind!r} (expected 'f1', 'exact_match', or 'rouge')")


def score_rows(
    rows: Sequence[dict[str, Any]],
    base_url: str,
    workspace: str,
    deployment_name: str,
    model_field: str,
    metric: MetricKind = "f1",
    max_tokens: int = 64,
    parallelism: int = 8,
    limit_samples: int | None = None,
    enable_thinking: bool = False,
) -> float:
    """Run one deterministic metric over ``rows`` and return its aggregate mean (0..1)."""
    from nemo_evaluator_sdk import Evaluator

    for index, row in enumerate(rows):
        assert_chat_row(row, index=index)

    target = _build_target(base_url, workspace, deployment_name, model_field)
    config = _build_config(max_tokens, parallelism, limit_samples, enable_thinking)
    result = Evaluator().run_sync(
        metrics=_metric(metric),
        dataset=list(rows),
        target=target,
        prompt_template=CHAT_USER_PROMPT_TEMPLATE,
        config=config,
    )
    score = result.aggregate_scores.scores[0]
    mean = score.mean if score.mean is not None else 0.0
    logger.info(
        "eval %s: metric=%s mean=%.4f (n=%d) via %s",
        model_field,
        metric,
        mean,
        len(rows),
        deployment_name,
    )
    return round(float(mean), 4)


@dataclass
class UpliftResult:
    """Base-vs-tuned comparison for one metric."""

    metric: MetricKind
    base_score: float
    tuned_score: float
    base_label: str = "base"
    tuned_label: str = "tuned"
    extras: dict[str, float] = field(default_factory=dict)

    @property
    def uplift(self) -> float:
        """tuned - base (positive = the fine-tune helped)."""
        return round(self.tuned_score - self.base_score, 4)

    def assert_ok(self, require_uplift: bool = False, tolerance: float = 0.02) -> None:
        """Assert the fine-tune did not regress (default) or strictly improved.

        Tiny e2e training runs rarely produce a large, stable uplift, so the default
        gate is non-regression within *tolerance*. Set ``require_uplift`` (env
        ``E2E_REQUIRE_UPLIFT=1`` in the tests) to require ``tuned > base``.
        """
        if require_uplift:
            assert self.tuned_score > self.base_score, (
                f"expected strict uplift on {self.metric}: "
                f"tuned={self.tuned_score} !> base={self.base_score} (uplift={self.uplift})"
            )
        else:
            assert self.tuned_score >= self.base_score - tolerance, (
                f"{self.metric} regressed beyond tolerance {tolerance}: "
                f"tuned={self.tuned_score} < base={self.base_score} (uplift={self.uplift})"
            )
