# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Binary-classification evaluator for the email phishing analyzer.

The stock NAT/RAGAS evaluators score answers with an LLM judge and report a single
continuous ``average_score``. The first-mile phishing demo instead needs the four
standard binary-classification metrics computed over the *whole* dataset from a
confusion matrix: recall (the headline metric), precision, accuracy, and F1.

Those metrics cannot be produced by averaging a per-item score, so this evaluator
overrides ``evaluate`` to compute TP/FP/FN/TN across every item and then emits the
requested metric as ``average_score``. List one evaluator entry per metric in the
eval config (each with a different ``metric``) so every number surfaces as its own
evaluator score — the same shape the platform's Evaluator job and Studio read.

Positive class = phishing (so recall = fraction of real phishing emails caught).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from nat.builder.builder import EvalBuilder
from nat.builder.evaluator import EvaluatorInfo
from nat.cli.register_workflow import register_evaluator
from nat.data_models.evaluator import EvalInput, EvaluatorBaseConfig
from nat.plugins.eval.data_models.evaluator_io import EvalOutput, EvalOutputItem
from pydantic import Field

from .utils import smart_parse

logger = logging.getLogger(__name__)

ClassificationMetric = Literal["recall", "precision", "accuracy", "f1"]


class EmailPhishingClassificationEvaluatorConfig(EvaluatorBaseConfig, name="email_phishing_classification"):
    """Configuration for the binary phishing-classification evaluator."""

    metric: ClassificationMetric = Field(
        default="recall",
        description="Which classification metric to expose as this evaluator's average_score.",
    )
    positive_label: str = Field(
        default="phishing",
        description="Label treated as the positive class (the class recall/precision are computed for).",
    )
    negative_label: str = Field(
        default="benign",
        description="Label treated as the negative class.",
    )


def _normalize(value: object) -> str:
    """Lower-case, stripped string form of an arbitrary label/answer object."""
    return str(value).strip().lower()


def predict_label(output_obj: object, positive_label: str, negative_label: str) -> str | None:
    """Derive a phishing/benign prediction from the workflow's output.

    The ReAct workflow is instructed to end with the word "phishing" or "benign",
    and the underlying tool returns JSON with an ``is_likely_phishing`` boolean.
    We handle both, plus loose free text, returning ``positive_label`` /
    ``negative_label`` / ``None`` (unparseable → counted as a miss).
    """
    pos = positive_label.lower()
    neg = negative_label.lower()

    if output_obj is None:
        return None

    text = output_obj if isinstance(output_obj, str) else str(output_obj)

    # Prefer an explicit structured verdict when the tool JSON is present.
    parsed = smart_parse(text)
    if isinstance(parsed, dict) and "is_likely_phishing" in parsed:
        flag = parsed["is_likely_phishing"]
        if isinstance(flag, str):
            flag = flag.strip().lower() in ("true", "yes", "1")
        return positive_label if flag else negative_label

    lowered = text.lower()
    has_pos = pos in lowered
    has_neg = neg in lowered
    if has_pos and not has_neg:
        return positive_label
    if has_neg and not has_pos:
        return negative_label
    if has_pos and has_neg:
        # Both mentioned (e.g. reasoning then a verdict): trust the last verdict.
        return positive_label if lowered.rfind(pos) > lowered.rfind(neg) else negative_label
    return None


def _metric_from_counts(metric: ClassificationMetric, tp: int, fp: int, fn: int, tn: int) -> float:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    total = tp + fp + fn + tn
    if metric == "precision":
        return precision
    if metric == "recall":
        return recall
    if metric == "accuracy":
        return (tp + tn) / total if total else 0.0
    if metric == "f1":
        return (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    raise ValueError(f"Unknown classification metric: {metric}")


def make_evaluate_fn(
    config: EmailPhishingClassificationEvaluatorConfig,
) -> Callable[[EvalInput], Awaitable[EvalOutput]]:
    """Build the async evaluate function for the given config."""

    async def evaluate(eval_input: EvalInput) -> EvalOutput:
        tp = fp = fn = tn = 0
        items: list[EvalOutputItem] = []

        for item in eval_input.eval_input_items:
            gold = _normalize(item.expected_output_obj)
            predicted = predict_label(item.output_obj, config.positive_label, config.negative_label)
            pred_norm = _normalize(predicted) if predicted is not None else None

            gold_is_positive = gold == config.positive_label.lower()
            pred_is_positive = pred_norm == config.positive_label.lower()

            if gold_is_positive and pred_is_positive:
                tp += 1
            elif (not gold_is_positive) and pred_is_positive:
                fp += 1
            elif gold_is_positive and (not pred_is_positive):
                fn += 1
            else:
                tn += 1

            correct = pred_norm is not None and pred_norm == gold
            items.append(
                EvalOutputItem(
                    id=item.id,
                    score=1.0 if correct else 0.0,
                    reasoning={
                        "predicted": predicted,
                        "expected": gold,
                        "correct": correct,
                    },
                )
            )

        score = round(_metric_from_counts(config.metric, tp, fp, fn, tn), 4)
        logger.info(
            "phishing classification [%s]=%.4f (tp=%d fp=%d fn=%d tn=%d)",
            config.metric,
            score,
            tp,
            fp,
            fn,
            tn,
        )
        return EvalOutput(average_score=score, eval_output_items=items)

    return evaluate


@register_evaluator(config_type=EmailPhishingClassificationEvaluatorConfig)
async def register_email_phishing_classification_evaluator(
    config: EmailPhishingClassificationEvaluatorConfig, _builder: EvalBuilder
):
    """Register the binary phishing-classification evaluator."""
    yield EvaluatorInfo(
        config=config,
        # NAT annotates evaluate_fn as returning EvalOutputLike synchronously, but
        # awaits it at runtime (its own tunable_rag_evaluator passes an async method
        # here too). EvalOutput structurally satisfies EvalOutputLike.
        evaluate_fn=make_evaluate_fn(config),  # ty: ignore[invalid-argument-type]
        description=f"Binary phishing-classification {config.metric} (positive class = {config.positive_label}).",
    )
