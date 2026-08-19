# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

import httpx
import pytest
from respx import MockRouter

from nemo_platform import NeMoPlatform


@pytest.mark.respx(base_url="http://127.0.0.1:4010")
def test_direct_span_ingest_sdk_sends_provider_neutral_batch(respx_mock: MockRouter) -> None:
    route = respx_mock.post("/apis/intake/v2/workspaces/default/ingest/spans").mock(return_value=httpx.Response(201))

    with NeMoPlatform(base_url="http://127.0.0.1:4010", workspace="default") as client:
        result = client.intake.ingest.spans.create(
            source="langsmith",
            spans=[
                {
                    "span_id": "span-1",
                    "trace_id": "trace-1",
                    "started_at": "2026-08-14T12:00:00Z",
                    "ended_at": "2026-08-14T12:00:01Z",
                    "kind": "LLM",
                    "status": "success",
                    "input": {"prompt": "hello"},
                    "attributes": {"langsmith.raw": {"revision_id": "rev-1"}},
                }
            ],
        )

    assert result is None
    assert route.called
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "source": "langsmith",
        "spans": [
            {
                "span_id": "span-1",
                "trace_id": "trace-1",
                "started_at": "2026-08-14T12:00:00Z",
                "ended_at": "2026-08-14T12:00:01Z",
                "kind": "LLM",
                "status": "success",
                "input": {"prompt": "hello"},
                "attributes": {"langsmith.raw": {"revision_id": "rev-1"}},
            }
        ],
    }
