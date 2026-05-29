# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trajectory metrics for evaluator agent benchmark rows."""

from math import nan

from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class TrajectoryEvidenceMetric:
    """Score basic trajectory availability and trajectory-derived signals."""

    def __init__(
        self,
        *,
        trajectory_summary_key: str,
        tool_call_count_key: str,
        failed_command_count_key: str,
        recovery_event_count_key: str,
    ) -> None:
        self.trajectory_summary_key = trajectory_summary_key
        self.tool_call_count_key = tool_call_count_key
        self.failed_command_count_key = failed_command_count_key
        self.recovery_event_count_key = recovery_event_count_key

    @property
    def type(self) -> str:
        return "agent_eval/trajectory_evidence"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.continuous_score("trajectory_present"),
            MetricOutputSpec.continuous_score("tool_call_count"),
            MetricOutputSpec.continuous_score("failed_command_count"),
            MetricOutputSpec.continuous_score("recovery_event_count"),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        item = input.row.data
        try:
            summary = item[self.trajectory_summary_key]
            if summary is None:
                trajectory_present = 0.0
                tool_call_count = 0.0
                failed_command_count = 0.0
                recovery_event_count = 0.0
            else:
                if not isinstance(summary, dict):
                    raise TypeError("Trajectory summary must be a dict or None")
                tool_call_count_value = summary[self.tool_call_count_key]
                failed_command_count_value = summary[self.failed_command_count_key]
                recovery_event_count_value = summary[self.recovery_event_count_key]
                if (
                    not isinstance(tool_call_count_value, int)
                    or not isinstance(failed_command_count_value, int)
                    or not isinstance(recovery_event_count_value, int)
                    or tool_call_count_value < 0
                    or failed_command_count_value < 0
                    or recovery_event_count_value < 0
                ):
                    raise TypeError("Trajectory summary counts must be non-negative ints")
                trajectory_present = 1.0
                tool_call_count = float(tool_call_count_value)
                failed_command_count = float(failed_command_count_value)
                recovery_event_count = float(recovery_event_count_value)
        except (KeyError, TypeError):
            trajectory_present = nan
            tool_call_count = nan
            failed_command_count = nan
            recovery_event_count = nan
        return MetricResult(
            outputs=[
                MetricOutput(name="trajectory_present", value=trajectory_present),
                MetricOutput(name="tool_call_count", value=tool_call_count),
                MetricOutput(name="failed_command_count", value=failed_command_count),
                MetricOutput(name="recovery_event_count", value=recovery_event_count),
            ]
        )
