# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``end_to_end_latency_ms`` computed field on EvaluationResponse.

It names ``latency_ms.sum`` — the test-case-weighted latency sum (per-test-case latency, with a
test case's attempts averaged, summed across test cases), i.e. end-to-end latency assuming tasks
run serially. The rollup already computes ``latency_ms.sum`` with that semantics; the field only
surfaces it so consumers don't have to know the convention.
"""

from nmp.intake.api.v2.experiments.schemas import EvaluationResponse, EvaluatorAggregate


def _response(latency: EvaluatorAggregate | None) -> EvaluationResponse:
    return EvaluationResponse(
        id="e",
        name="e",
        workspace="default",
        experiment_ids=["grp"],
        dataset_name="ds",
        latency_ms=latency,
    )


def test_end_to_end_latency_equals_latency_sum() -> None:
    resp = _response(EvaluatorAggregate(sum=1234.5, mean=411.5, count=3))
    assert resp.end_to_end_latency_ms == 1234.5
    # and it serializes under the field name
    assert resp.model_dump()["end_to_end_latency_ms"] == 1234.5


def test_end_to_end_latency_is_none_without_latency() -> None:
    assert _response(None).end_to_end_latency_ms is None
    # latency present but no summable value (no session carried latency)
    assert _response(EvaluatorAggregate()).end_to_end_latency_ms is None
