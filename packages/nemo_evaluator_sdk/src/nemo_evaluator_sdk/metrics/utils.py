# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for runtime metrics."""

import re
import string

from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.metrics.protocol import Metric


def normalize_text(s: str) -> str:
    """Normalize free-form text for token/equality-based metric comparisons."""
    if not s:
        return ""
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def metric_type_name(metric: Metric) -> str:
    """Resolve a stable public type name for one runtime metric.

    Args:
        metric: Metric object used during execution or optimization.

    Returns:
        ``metric.type.value`` for built-in ``MetricType`` members, otherwise
        the custom string metric type, otherwise the metric class name.

    This helper exists for generic call sites that operate on the runtime
    ``Metric`` protocol and must support the documented ``Metric.type`` shapes
    without depending on enum-only APIs:

    - built-in ``MetricType`` members
    - plain string custom metric types
    - custom string-based enum members, such as ``class MyMetricType(str, Enum)``

    Examples:
        Built-in metrics still commonly expose ``MetricType`` members, so a
        BLEU runtime metric resolves to ``"bleu"`` via ``metric.type.value``.

        Custom metrics may expose ``type`` as a plain string such as
        ``"my-custom-metric"``, or as a custom string-based enum member; both
        are returned as their string identifier.
    """
    metric_type = getattr(metric, "type", None)
    if isinstance(metric_type, MetricType):
        return metric_type.value
    if isinstance(metric_type, str):
        return metric_type
    return metric.__class__.__name__
