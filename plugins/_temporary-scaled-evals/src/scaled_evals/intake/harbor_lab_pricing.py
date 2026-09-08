# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pinned Harbor Lab pricing subset for routed-model session totals."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

HARBOR_LAB_REVISION = "58263c774df8d5071d85295f51713ace48993e88"
HARBOR_LAB_PRICING_SOURCE = f"harbor-lab@{HARBOR_LAB_REVISION}"

_DATA_DIR = Path(__file__).parents[1] / "data"
_OVERRIDES_FILE = _DATA_DIR / "harbor_lab_pricing_overrides.json"
_CATALOG_FILE = _DATA_DIR / "harbor_lab_pricing_catalog.json"
_ROUTING_PREFIXES = (
    "nvidia/aws/anthropic/",
    "nvidia/gcp/google/",
    "nvidia/us/azure/openai/",
    "nvidia/nvidia/nvidia/",
    "nvidia/nvidia/",
    "nvidia/",
    "openai/aws/anthropic/",
    "openai/openai/",
    "aws/anthropic/",
    "azure/openai/",
    "azure/anthropic/",
    "azure/",
    "gcp/google/",
    "anthropic/",
    "openai/",
)


def _pricing_entries(path: Path) -> dict[str, dict[str, Any]]:
    # Optional by design: only the catalog ships. A deployment that prices models
    # absent from it drops an overrides file next to this one, so the merge below
    # has to tolerate the file not being there.
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        key: value
        for key, value in raw.items()
        if isinstance(value, dict) and value.get("input_cost_per_token") is not None
    }


@lru_cache(maxsize=1)
def pricing_catalog() -> dict[str, dict[str, Any]]:
    """Return the curated catalog, with any deployment overrides taking precedence."""
    return {**_pricing_entries(_CATALOG_FILE), **_pricing_entries(_OVERRIDES_FILE)}


def resolve_model(model_name: str, pricing: dict[str, dict[str, Any]]) -> str | None:
    """Resolve a routed model name using Harbor Lab's prefix-stripping rules."""
    model_name = model_name.replace(":", "/", 1)
    if model_name in pricing:
        return model_name

    stripped = model_name
    while True:
        for prefix in _ROUTING_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :]
                break
        else:
            break

    if stripped != model_name and stripped in pricing:
        return stripped

    vendor_model = re.match(r"^[^/]+/(.+)$", stripped)
    if vendor_model and vendor_model.group(1) in pricing:
        return vendor_model.group(1)

    normalized = re.sub(r"^bedrock-", "", stripped)
    normalized = re.sub(r"-nothink$", "", normalized)
    normalized = re.sub(r"-v\d+(?::\d+)?$", "", normalized)
    if normalized != stripped and normalized in pricing:
        return normalized
    return None


def estimate_cost(
    model_name: str,
    input_tokens: int,
    cache_tokens: int,
    cache_creation_tokens: int,
    output_tokens: int,
) -> dict[str, Any] | None:
    """Estimate aggregate model cost with Harbor Lab's cache-aware math."""
    pricing = pricing_catalog()
    matched = resolve_model(model_name, pricing)
    if matched is None:
        return None

    entry = pricing[matched]
    input_rate = float(entry["input_cost_per_token"])
    output_rate = float(entry.get("output_cost_per_token", 0))
    cache_rate = float(entry.get("cache_read_input_token_cost", input_rate))
    cache_creation_rate = float(entry.get("cache_creation_input_token_cost", input_rate))
    bounded_cache_tokens = min(max(cache_tokens, 0), max(input_tokens, 0))
    remaining_input_tokens = max(input_tokens, 0) - bounded_cache_tokens
    bounded_cache_creation_tokens = min(max(cache_creation_tokens, 0), remaining_input_tokens)
    non_cached_tokens = remaining_input_tokens - bounded_cache_creation_tokens
    input_cost = non_cached_tokens * input_rate
    cache_cost = bounded_cache_tokens * cache_rate
    cache_creation_cost = bounded_cache_creation_tokens * cache_creation_rate
    output_cost = max(output_tokens, 0) * output_rate
    return {
        "input_cost": input_cost,
        "cache_cost": cache_cost,
        "cache_creation_cost": cache_creation_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + cache_cost + cache_creation_cost + output_cost,
        "matched_model": matched,
    }
