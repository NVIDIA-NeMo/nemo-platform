# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RetrievalProfile = Literal["embed", "rerank"]

DEFAULT_QUERY_COUNTS = {"multi_hop": 3, "structural": 2, "contextual": 2}
DEFAULT_REASONING_COUNTS = {
    "factual": 1,
    "relational": 1,
    "inferential": 1,
    "temporal": 1,
    "procedural": 1,
    "causal": 1,
    "visual": 1,
}


@dataclass(frozen=True)
class ProfileModels:
    chat_model: str
    embed_model: str


_PROFILE_MODELS: dict[str, ProfileModels] = {
    "embed": ProfileModels(
        chat_model="nvidia/nemotron-3-ultra-550b-a55b",
        embed_model="nvidia/nemotron-3-embed-1b",
    ),
    "rerank": ProfileModels(
        chat_model="nvidia/nemotron-3-nano-30b-a3b",
        embed_model="nvidia/llama-3.2-nv-embedqa-1b-v2",
    ),
}


def profile_models(profile: RetrievalProfile) -> ProfileModels:
    return _PROFILE_MODELS[profile]
