# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RAGAS metrics must preserve runtime default headers when building provider clients.

The platform forwards caller identity by stamping ``Model.default_headers`` onto resolved
models; dropping them here silently strips the caller's identity from judge/embeddings calls.
"""

from typing import Any, cast

import httpx
from nemo_evaluator_sdk.metrics.ragas import ResponseRelevancyMetric
from nemo_evaluator_sdk.values import Model

CALLER_HEADERS = {"X-NMP-Principal-Id": "user@example.com"}


def _metric_with_headers() -> ResponseRelevancyMetric:
    return ResponseRelevancyMetric(
        judge_model=Model(
            name="gpt-4",
            url="https://model.com/v1/chat/completions",
            default_headers=CALLER_HEADERS,
        ),
        embeddings_model=Model(
            name="embed",
            url="https://model.com/v1/embeddings",
            default_headers=CALLER_HEADERS,
        ),
    )


def test_default_headers_reach_client_configuration() -> None:
    metric = _metric_with_headers()

    assert metric._llm_model is not None
    assert metric._llm_model["default_headers"] == CALLER_HEADERS
    assert metric._embed_params is not None
    assert metric._embed_params["default_headers"] == CALLER_HEADERS


def test_default_headers_reach_judge_and_embeddings_clients() -> None:
    metric = _metric_with_headers()

    llm_judge = metric._get_llm_judge(httpx.AsyncClient())
    assert llm_judge is not None
    # The wrapped client is typed as a generic BaseLanguageModel; the concrete ChatOpenAI
    # carries default_headers.
    assert cast(Any, llm_judge).langchain_llm.default_headers == CALLER_HEADERS

    embeddings = metric._get_embeddings_client()
    assert embeddings is not None
    assert cast(Any, embeddings).embeddings.default_headers == CALLER_HEADERS
