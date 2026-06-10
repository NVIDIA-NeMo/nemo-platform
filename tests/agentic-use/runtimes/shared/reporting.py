# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility shim — gating was promoted to the Evaluator SDK.

Import from ``nemo_evaluator_sdk.agent_eval.gating`` directly; this module
re-exports the same symbols so existing adapter imports keep working.
"""

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval.gating import (
    DEFAULT_REWARD_OUTPUTS,
    GateCheck,
    GateReport,
    GateThresholds,
    evaluate_gate,
    load_baseline_summary,
    run_gate_checks,
    summarize_run,
    write_gate_report,
)

__all__ = [
    "DEFAULT_REWARD_OUTPUTS",
    "GateCheck",
    "GateReport",
    "GateThresholds",
    "evaluate_gate",
    "load_baseline_summary",
    "run_gate_checks",
    "summarize_run",
    "write_gate_report",
]
