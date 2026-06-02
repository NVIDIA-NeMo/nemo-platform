# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sample payload adapters for evaluator SDK execution."""

from typing import Any

from nemo_platform.beta.evaluator.metrics.protocol import CandidateOutput, DatasetRow, MetricInput

_CANDIDATE_SAMPLE_FIELDS = frozenset({"output_text", "response", "trajectory"})


def build_offline_sample(row: dict[str, Any]) -> dict[str, Any]:
    """Build the sample payload for an offline row.

    Field mapping can normalize an offline prediction into the canonical
    ``output`` row field. Surface that value as ``sample.output_text`` so
    protocol metrics see the same candidate location as online evaluations.
    """
    output = row.get("output")
    if isinstance(output, str):
        return {"output_text": output}
    return {}


def build_metric_input(row: dict[str, Any], sample: dict[str, Any], index: int | None = None) -> MetricInput:
    """Build the metric protocol input from dataset row and generated sample payloads."""
    output_text = sample.get("output_text")
    metadata = {
        key: value
        for key, value in sample.items()
        if key not in _CANDIDATE_SAMPLE_FIELDS or (key == "output_text" and not isinstance(output_text, str))
    }
    return MetricInput(
        row=DatasetRow(row_index=index, data=row),
        candidate=CandidateOutput(
            output_text=output_text if isinstance(output_text, str) else None,
            response=sample.get("response"),
            trajectory=sample.get("trajectory"),
            metadata=metadata,
        ),
    )
