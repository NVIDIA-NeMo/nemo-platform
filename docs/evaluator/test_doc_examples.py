#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract checks for the Evaluator SDK patterns used in these docs.

The Evaluator docs are written against the ``nemo_evaluator`` plugin SDK
(``evaluator.run(...)`` / ``evaluator.run(...)``), not the old
``/v2/.../evaluation/metrics/jobs`` REST endpoints. This module validates the
import paths and call contract that every runnable doc snippet relies on, so the
docs cannot silently drift from the SDK again.

These checks run fully offline: they exercise import locations and the packager
contract for ``Evaluator.submit`` — built-in metrics bundle inline and need no
packager, while custom metrics require an explicit one. They do not submit jobs
and need no running platform or model credentials.

Run directly:
    uv run python docs/evaluator/test_doc_examples.py

Or under pytest:
    uv run pytest docs/evaluator/test_doc_examples.py -v
"""

from __future__ import annotations

import inspect

import pytest
from nemo_evaluator.sdk import Evaluator
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackagerPolicyError
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_platform import NeMoPlatform


class _CustomMetric:
    """A metric that is not a built-in type (cannot be reconstructed from config)."""

    type = "custom-score"
    description = "custom metric"
    labels: dict[str, str] = {}

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


def test_filesetref_imports_from_platform_sdk() -> None:
    """Docs import ``FilesetRef`` from ``nemo_evaluator.sdk`` (platform helpers)."""
    from nemo_evaluator.sdk import FilesetRef

    assert FilesetRef is not None


def test_filesetref_is_not_in_nemo_evaluator_sdk_values() -> None:
    """``FilesetRef`` is NOT exported from ``nemo_evaluator_sdk.values``.

    The LLM Judge tutorial previously imported it from the wrong module, which
    fails at import time. Guard against that regression.
    """
    import nemo_evaluator_sdk.values as values

    assert not hasattr(values, "FilesetRef")


def test_modelref_imports_from_context_agnostic_sdk() -> None:
    """Docs import ``ModelRef`` from ``nemo_evaluator_sdk`` (value types)."""
    from nemo_evaluator_sdk import ModelRef

    assert ModelRef is not None


def test_cloudpickle_packager_import_path() -> None:
    """Durable-submit docs import the packager from this exact path."""
    from nemo_evaluator.shared.metric_bundles.cloudpickle import (
        CloudpickleMetricBundlePackager,
    )

    assert CloudpickleMetricBundlePackager is not None


def _evaluator() -> Evaluator:
    """Build an Evaluator resource without contacting any service.

    Client construction and the ``submit`` argument guard are both offline; the
    guard runs before any executor/HTTP work.
    """
    client = NeMoPlatform(base_url="http://localhost:8080", workspace="default")
    return client.evaluator


def test_platform_methods_take_a_metric_bundle_packager() -> None:
    """Both platform paths take ``metric_bundle_packager``, because metrics cross the wire.

    This previously contrasted ``submit`` against a local ``run``. The plugin no longer executes
    locally, so there is no longer a method that skips packaging.
    """
    from nemo_evaluator.sdk import Evaluator

    for method in (Evaluator.evaluate_dataset, Evaluator.evaluate):
        assert "metric_bundle_packager" in inspect.signature(method).parameters


def test_builtin_metric_does_not_require_a_packager() -> None:
    """Built-in metrics bundle inline, so docs omit the packager on ``submit()``.

    Packager resolution happens before delegating to the executor, so we stub the
    executor with a sentinel: reaching it (rather than raising a packager-policy
    error) proves the built-in metric bundled inline with no packager required —
    without depending on a live service or swallowing unrelated failures.
    """
    from unittest.mock import patch

    from nemo_evaluator_sdk import ExactMatchMetric

    evaluator = _evaluator()
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = [{"expected": "Paris", "output": "Paris"}]
    sentinel = RuntimeError("reached executor.evaluate_dataset (packaging resolved without a packager)")

    with patch.object(evaluator._executor, "evaluate_dataset", side_effect=sentinel):
        with pytest.raises(RuntimeError, match="reached executor.evaluate_dataset"):
            evaluator.evaluate_dataset(metrics=[metric], dataset=dataset)


def test_custom_metric_requires_an_explicit_packager() -> None:
    """Custom (non-built-in) metrics still require an explicit packager to reach the platform."""
    evaluator = _evaluator()
    dataset = [{"expected": "Paris", "output": "Paris"}]

    with pytest.raises(MetricBundlePackagerPolicyError, match="CloudpickleMetricBundlePackager"):
        evaluator.evaluate_dataset(metrics=[_CustomMetric()], dataset=dataset)


def main() -> None:
    raise SystemExit(pytest.main([__file__, "-v"]))


if __name__ == "__main__":
    main()
