# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for JobsServiceProgressReporter's status_details handling.

Focused on metric preservation: the Jobs service REPLACES ``status_details``, and
the runner reports checkpoint processing, completion and failure from a different
process than the training driver that accumulated the loss curve. Without the
carry-over in ``update_task`` every job ends by erasing its own metrics.
"""

from __future__ import annotations

from typing import Any

import pytest
from nmp.customization_common.training.progress import JobsServiceProgressReporter

SERIES: dict[str, list[dict[str, float | int]]] = {
    "train_loss": [{"step": 10, "epoch": 1, "value": 0.5}],
    "val_loss": [{"step": 10, "epoch": 1, "value": 0.45}],
}
EMPTY: dict[str, list[dict[str, float | int]]] = {"train_loss": [], "val_loss": []}


class _JobCtx:
    """The four identifiers update_task reads off the job context."""

    normalized_task = "training"
    workspace = "default"
    job_id = "job-1"
    step = "train"


class _Reporter(JobsServiceProgressReporter):
    """Reporter with the SDK and job context stubbed out.

    Bypasses ``__init__`` rather than mocking the SDK factory: what is under test
    is the status_details logic, and the real constructor calls ``get_task_sdk``,
    which wants credentials. Every attribute ``update_task`` touches is set here.
    """

    def __init__(self, stored: dict[str, list[dict[str, float | int]]]) -> None:
        self._job_ctx = _JobCtx()  # type: ignore[assignment] - duck-typed stand-in
        self._sdk = object()  # type: ignore[assignment] - never dereferenced; the client is patched
        self._is_main_rank = True
        self._enabled = True
        self._max_steps = 0
        self._num_epochs = 0
        self._stored = stored
        self.fetch_calls = 0

    def fetch_current_metrics(self) -> dict[str, list[dict[str, float | int]]]:
        self.fetch_calls += 1
        return self._stored


class _StubJobsClient:
    """Captures task updates instead of issuing them."""

    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def update_job_step_task(self, **kwargs: Any) -> None:
        self._sink.append(kwargs)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what ``update_task`` would send, running its real body.

    ``update_task`` swallows exceptions, so anything wrong with the stubs would
    surface as an empty capture; the helpers below index into it eagerly so that
    reads as a failure rather than a pass.
    """
    sink: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "nmp.customization_common.training.progress.client_from_platform",
        lambda _sdk, _cls: _StubJobsClient(sink),
    )
    return sink


def _details(sent: list[dict[str, Any]]) -> dict[str, Any]:
    assert len(sent) == 1, f"expected exactly one task update, got {len(sent)}"
    return dict(sent[0]["body"].status_details or {})


# --------------------------------------------------------------------------- #
# Preservation
# --------------------------------------------------------------------------- #


def test_completion_preserves_the_accumulated_series(sent: list[dict[str, Any]]) -> None:
    """The last write of a successful job must not blank the loss curve."""
    _Reporter(SERIES).report_completed("Training completed")

    details = _details(sent)
    assert details["metrics"] == SERIES
    assert details["phase"] == "completed"


def test_failure_preserves_the_accumulated_series(sent: list[dict[str, Any]]) -> None:
    """A failed run is exactly when the partial curve is most worth keeping."""
    _Reporter(SERIES).report_error("boom")

    assert _details(sent)["metrics"] == SERIES


def test_intermediate_phase_preserves_the_accumulated_series(sent: list[dict[str, Any]]) -> None:
    """processing_checkpoint fires after the driver exits, before completion."""
    _Reporter(SERIES).report_running("processing_checkpoint")

    details = _details(sent)
    assert details["metrics"] == SERIES
    assert details["phase"] == "processing_checkpoint"


def test_caller_supplied_metrics_win_and_skip_the_fetch(sent: list[dict[str, Any]]) -> None:
    """Per-step training reports carry their own series; no round-trip for them."""
    fresher = {"train_loss": [{"step": 20, "epoch": 2, "value": 0.1}], "val_loss": []}
    reporter = _Reporter(SERIES)

    reporter.report_running("training", step=20, metrics=fresher)

    assert _details(sent)["metrics"] == fresher
    assert reporter.fetch_calls == 0


def test_no_stored_metrics_adds_no_key(sent: list[dict[str, Any]]) -> None:
    """Before training starts there is nothing to preserve; don't invent a key."""
    _Reporter(EMPTY).report_running("compiling_config")

    assert "metrics" not in _details(sent)


def test_preservation_does_not_resurrect_stale_current_state(sent: list[dict[str, Any]]) -> None:
    """Only the cumulative field carries over, not the step/lr snapshot."""
    _Reporter(SERIES).report_completed("Training completed")

    assert set(_details(sent)) == {"message", "phase", "metrics"}


def test_error_details_still_ride_along(sent: list[dict[str, Any]]) -> None:
    """Preserving metrics must not displace the error payload."""
    _Reporter(SERIES).report_error({"message": "oom", "code": "OOM"})

    assert sent[0]["body"].error_details == {"message": "oom", "code": "OOM"}


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #


def test_disabled_reporter_sends_nothing_and_does_not_fetch(sent: list[dict[str, Any]]) -> None:
    reporter = _Reporter(SERIES)
    reporter._enabled = False

    reporter.report_completed("Training completed")

    assert sent == []
    assert reporter.fetch_calls == 0


def test_non_main_rank_sends_nothing(sent: list[dict[str, Any]]) -> None:
    reporter = _Reporter(SERIES)
    reporter._is_main_rank = False

    reporter.report_completed("Training completed")

    assert sent == []
