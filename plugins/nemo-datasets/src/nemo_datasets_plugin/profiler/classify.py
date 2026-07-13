# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Classification: assign column roles, resolve the format/prompt-form axes, and pick a dataset type.

Roles are inferred from column names, gated by dtype, and stacked onto the feature nodes as
``semantic_role`` markers. The dataset type is the most specific structure the assigned roles
satisfy. Verifiability and content-probe corroboration are added by a later stage.
"""

from __future__ import annotations

import re

from nemo_platform_plugin.files.dataset_profile import (
    ColumnStats,
    Evidence,
    FeatureSchema,
    PartitionClassification,
    Verifiability,
)

# Column-name aliases -> role. Score is handled separately (name alias + numeric dtype gate).
_ALIAS_ROLES = {
    "prompt": "prompt",
    "question": "prompt",
    "instruction": "prompt",
    "problem": "prompt",
    "query": "prompt",
    "context": "context",
    "input": "context",
    "passage": "context",
    "document": "context",
    "system": "system",
    "system_prompt": "system",
    "response": "completion",
    "output": "completion",
    "answer": "completion",
    "completion": "completion",
    "solution": "completion",
    "messages": "messages",
    "conversation": "messages",
    "conversations": "messages",
    "chosen": "chosen",
    "rejected": "rejected",
    "label": "label",
    "rank": "rank",
    "ground_truth": "ground_truth",
    "reference_answer": "ground_truth",
    "verification_info": "ground_truth",
    "test_cases": "ground_truth",
    "completions": "stepwise_completions",
    "labels": "stepwise_labels",
    "tools": "tools",
    "image": "image",
    "images": "image",
    "id": "id",
    "prompt_id": "id",
    "source": "provenance",
    "dataset": "provenance",
    "model": "provenance",
    "category": "meta",
}

_SCORE_ALIASES = {
    "score",
    "score_chosen",
    "score_rejected",
    "helpfulness",
    "correctness",
    "coherence",
    "complexity",
    "verbosity",
    "quality",
    "rating",
    "reward",
}

_TEXT_DTYPES = {"string", "messages"}
# A verification target is naturally a container: test_cases (list), verification_info (struct), or a
# plain string answer — but never a bare scalar/number, which is far more likely a label or score.
_GROUND_TRUTH_DTYPES = {"string", "messages", "list", "struct", "json"}
# Roles whose string-vs-messages dtype decides the format axis.
_SHAPE_ROLES = {"prompt", "completion", "chosen", "rejected", "messages"}


def _is_numeric(dtype: str) -> bool:
    return dtype.startswith(("int", "uint", "float"))


def _role_for(feature: FeatureSchema) -> str | None:
    name = feature.name.lower()
    dtype = feature.dtype
    if name in _SCORE_ALIASES and _is_numeric(dtype):
        return "score"
    if name == "label" and dtype == "bool":
        return "label"

    role = _ALIAS_ROLES.get(name)
    if role is None:
        return None
    # dtype gates: reject an alias whose dtype contradicts the role.
    if role == "messages" and dtype != "messages":
        return None
    if role in {"prompt", "completion", "chosen", "rejected", "context", "system"}:
        if dtype not in _TEXT_DTYPES:
            return None
    if role == "ground_truth" and dtype not in _GROUND_TRUTH_DTYPES:
        return None
    if role == "rank" and not _is_numeric(dtype):
        return None
    if role in {"stepwise_completions", "stepwise_labels"} and dtype != "list":
        return None
    if role == "label":  # "label" reached here only when not bool
        return None
    return role


def _assign_roles(features: list[FeatureSchema]) -> None:
    for feature in features:
        role = _role_for(feature)
        if role is not None:
            feature.semantic_role = role


def _detect_modality(features: list[FeatureSchema]) -> str:
    if any(feature.semantic_role == "image" or feature.dtype == "image" for feature in features):
        return "image_text"
    return "text"


def _detect_format(features: list[FeatureSchema]) -> str | None:
    dtypes = {feature.dtype for feature in features if feature.semantic_role in _SHAPE_ROLES}
    has_messages = "messages" in dtypes
    has_string = "string" in dtypes
    if has_messages and has_string:
        return "mixed"
    if has_messages:
        return "conversational"
    if has_string:
        return "standard"
    return None


def _detect_prompt_form(roles: set[str]) -> str | None:
    if "prompt" in roles:
        return "explicit"
    if roles & {"chosen", "rejected", "completion"}:
        return "implicit"  # a prompt exists but is embedded in the completions
    return "n/a"


def _messages_stats(features: list[FeatureSchema], stats: dict[str, ColumnStats]):
    for feature in features:
        if feature.semantic_role == "messages":
            column = stats.get(feature.name)
            if column is not None:
                return column.messages
    return None


def _detect_type(features: list[FeatureSchema], stats: dict[str, ColumnStats]) -> str:
    roles = {feature.semantic_role for feature in features if feature.semantic_role}

    def has(*required: str) -> bool:
        return all(role in roles for role in required)

    if has("prompt", "stepwise_completions", "stepwise_labels"):
        return "stepwise_supervision"
    if has("rank"):
        return "ranked_responses"
    if has("prompt", "completion", "score"):
        return "scored_response"
    if has("prompt", "completion", "label"):
        return "unpaired_preference"
    if has("chosen", "rejected"):
        return "preference_pair"
    if has("prompt", "completion"):
        return "prompt_completion"
    if "messages" in roles:
        message_stats = _messages_stats(features, stats)
        if message_stats is not None and message_stats.ends_with_assistant_rate < 0.5:
            return "prompt_only"  # a chat that ends on a user turn has no training target
        return "messages"
    if "prompt" in roles:
        return "prompt_only"
    if len(features) == 1 and features[0].dtype == "string" and features[0].semantic_role is None:
        return "text"
    return "unknown"


# --- content probes ------------------------------------------------------------------------------

_TRANSCRIPT_MARKER = re.compile(r"\n\n(?:Human|Assistant|User):")
_GSM8K_ANSWER = re.compile(r"####\s*-?[\d.,/]+\s*$")
_BOXED_ANSWER = re.compile(r"\\boxed\{")


def _pct(fraction: float) -> str:
    return f"{round(fraction * 100)}%"


def _completion_texts(features: list[FeatureSchema], rows: list[dict]) -> list[str]:
    completion = next((feature for feature in features if feature.semantic_role == "completion"), None)
    if completion is None:
        return []
    texts: list[str] = []
    for row in rows:
        value = row.get(completion.name)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, list) and value and isinstance(value[-1], dict):
            content = value[-1].get("content")  # the final assistant turn for a conversational completion
            if isinstance(content, str):
                texts.append(content)
    return texts


def _detect_verifiability(features: list[FeatureSchema], rows: list[dict]) -> Verifiability | None:
    if not rows:
        return None

    ground_truth = next((feature for feature in features if feature.semantic_role == "ground_truth"), None)
    if ground_truth is not None:
        present = sum(1 for row in rows if row.get(ground_truth.name) not in (None, "", []))
        coverage = present / len(rows)
        detail = f"'{ground_truth.name}' present in {_pct(coverage)} of {len(rows)} sampled rows"
        return Verifiability(
            method="ground_truth_column", coverage=coverage, evidence=[Evidence(kind="content_probe", detail=detail)]
        )

    texts = _completion_texts(features, rows)
    if texts:
        hits = sum(1 for text in texts if _GSM8K_ANSWER.search(text) or _BOXED_ANSWER.search(text))
        if hits:
            coverage = hits / len(texts)
            detail = f"completion ends with an extractable answer (#### or \\boxed) in {_pct(coverage)} of {len(texts)} sampled rows"
            return Verifiability(
                method="extractable_final_answer",
                coverage=coverage,
                evidence=[Evidence(kind="content_probe", detail=detail)],
            )
    return None


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _implicit_prompt_evidence(features: list[FeatureSchema], rows: list[dict]) -> Evidence | None:
    if not rows:
        return None

    targets = [f for f in features if f.semantic_role in {"chosen", "rejected", "completion"} and f.dtype == "string"]
    texts = [value for f in targets for row in rows if isinstance((value := row.get(f.name)), str)]
    if texts:
        marked = sum(1 for text in texts if _TRANSCRIPT_MARKER.search(text))
        if marked:
            detail = f"embedded transcript markers in {_pct(marked / len(texts))} of sampled completions - prompt is embedded"
            return Evidence(kind="content_probe", detail=detail)

    chosen = next((f for f in features if f.semantic_role == "chosen" and f.dtype == "string"), None)
    rejected = next((f for f in features if f.semantic_role == "rejected" and f.dtype == "string"), None)
    if chosen is not None and rejected is not None:
        pairs = 0
        shared = 0
        for row in rows:
            left, right = row.get(chosen.name), row.get(rejected.name)
            if isinstance(left, str) and isinstance(right, str):
                pairs += 1
                if _common_prefix_len(left, right) >= 16:
                    shared += 1
        if pairs and shared / pairs >= 0.5:
            detail = f"chosen/rejected share a common prefix in {_pct(shared / pairs)} of pairs - prompt is embedded"
            return Evidence(kind="content_probe", detail=detail)
    return None


def classify(
    features: list[FeatureSchema], stats: dict[str, ColumnStats], rows: list[dict] | None = None
) -> PartitionClassification:
    """Assign roles onto ``features`` in place and return the partition's classification.

    ``rows`` (the sampled rows) drive the content probes — verifiability and implicit-prompt
    detection; role/axis/type inference needs only the schema and stats.
    """
    rows = rows or []
    _assign_roles(features)
    roles = {feature.semantic_role for feature in features if feature.semantic_role}
    dataset_type = _detect_type(features, stats)
    fmt = _detect_format(features)
    prompt_form = _detect_prompt_form(roles) if dataset_type != "unknown" else None

    evidence: list[Evidence] = []
    role_columns = [f"{feature.name} -> {feature.semantic_role}" for feature in features if feature.semantic_role]
    if role_columns:
        evidence.append(Evidence(kind="column_name", detail=f"columns matched roles: {', '.join(role_columns)}"))
    if fmt is not None:
        evidence.append(Evidence(kind="column_dtype", detail=f"{fmt} format from role column dtypes"))
    if prompt_form == "implicit":
        embedded = _implicit_prompt_evidence(features, rows)
        if embedded is not None:
            evidence.append(embedded)

    return PartitionClassification(
        modality=_detect_modality(features),
        dataset_type=dataset_type,
        format=fmt,
        prompt_form=prompt_form,
        verifiability=_detect_verifiability(features, rows),
        evidence=evidence,
    )
