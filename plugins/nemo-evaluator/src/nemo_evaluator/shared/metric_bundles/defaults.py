# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Default metric bundle packager selection.

Encapsulates the policy for choosing a packager when the caller does not provide
one explicitly. Built-in metric types use the inline packager (config-serialized,
no code execution). Custom metrics can fall back to cloudpickle for synchronous
``run`` calls, while durable ``submit``/``create`` calls require an explicit
cloudpickle opt-in.
"""

from __future__ import annotations

from collections.abc import Sequence

from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundlePackager,
    MetricBundlePackagerPolicyError,
)
from nemo_evaluator.shared.metric_bundles.hybrid import HybridMetricBundlePackager
from nemo_evaluator.shared.metric_bundles.inline import InlineMetricBundlePackager, inline_bundle_supported
from nemo_evaluator_sdk.metrics.protocol import Metric


def resolve_default_metric_bundle_packager(
    metric: Metric | Sequence[Metric],
    explicit: MetricBundlePackager | None,
    *,
    allow_cloudpickle_fallback: bool,
    action: str,
) -> MetricBundlePackager:
    """Resolve the packager to use for one or more metrics.

    An explicit packager is always honored. Otherwise the inline packager is used
    when every metric is a built-in type. When a custom metric is present and
    ``allow_cloudpickle_fallback=True``, the hybrid packager keeps built-in
    metrics inline and cloudpickles only the custom metric; callers that disable
    the fallback require an explicit opt-in instead.

    Args:
        metric: A runtime metric, or a sequence of them (one packager applies to all).
        explicit: A caller-provided packager, if any.
        allow_cloudpickle_fallback: Whether custom metrics may default to cloudpickle.
        action: Verb describing the operation, used in the error message.

    Returns:
        The packager to bundle the metric(s) with.

    Raises:
        MetricBundlePackagerPolicyError: When a custom metric needs an explicit
            packager and no fallback is allowed.
    """
    if explicit is not None:
        return explicit
    metrics = metric if isinstance(metric, Sequence) and not isinstance(metric, (str, bytes)) else [metric]
    if all(inline_bundle_supported(item) for item in metrics):
        return InlineMetricBundlePackager()
    if allow_cloudpickle_fallback:
        return HybridMetricBundlePackager()
    raise MetricBundlePackagerPolicyError(
        f"{action} a custom metric requires an explicit metric_bundle_packager; "
        "pass HybridMetricBundlePackager() (recommended — built-in metrics stay inline) "
        "or CloudpickleMetricBundlePackager() to bundle the metric code."
    )
