# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility re-exports for metric value types.

Metric value models now live in ``nemo_evaluator_sdk.values.metrics``.
This module is kept for backward compatibility with existing service imports.
"""

from nemo_evaluator_sdk.metrics.types import MetricsUnion
from nemo_evaluator_sdk.values import MetricBase as MetricBase
from pydantic import TypeAdapter

Metric = MetricsUnion

MetricAdapter = TypeAdapter(Metric)
