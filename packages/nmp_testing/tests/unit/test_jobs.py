# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for job-waiting utilities.

Tests the refactored wait_for_platform_job() which delegates to
poll_until_terminal() so that image-pull time (pending status) is not
counted against the main job-execution timeout.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from nmp.testing.e2e.jobs import TERMINAL_STATUSES, wait_for_platform_job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(data):
    """Wrap a payload in a NemoResponse-like object whose ``.data()`` returns it.

    Production now consumes typed-client responses via ``client.<op>(...).data()``,
    so mocked jobs-client methods must return an object with a ``.data()`` accessor
    rather than the payload directly.
    """
    m = MagicMock()
    m.data.return_value = data
    return m


def _make_jobs_client(*statuses: str) -> MagicMock:
    """Return a typed jobs-client mock whose get_job() cycles through *statuses*.

    Each ``get_job`` call returns a ``_resp(job)`` where ``job.status`` is the next
    status in *statuses*. ``get_job_status`` returns a ``_resp`` around a model with
    an empty ``model_dump``.
    """
    jobs_client = MagicMock()
    responses = []
    for s in statuses:
        j = MagicMock()
        j.status = s
        responses.append(_resp(j))
    jobs_client.get_job.side_effect = responses
    jobs_client.get_job_status.return_value = _resp(MagicMock(model_dump=MagicMock(return_value={})))
    return jobs_client


@contextmanager
def _patch_client(jobs_client: MagicMock):
    """Patch ``client_from_platform`` in the production module to return *jobs_client*."""
    with patch("nmp.testing.e2e.jobs.client_from_platform", return_value=jobs_client):
        yield


def _make_sdk(*statuses: str) -> MagicMock:
    """Return an SDK mock (unused by production routing, kept for call signatures)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Basic terminal-status behaviour
# ---------------------------------------------------------------------------


class TestWaitForPlatformJobTerminalStatus:
    """Tests that wait_for_platform_job returns on terminal statuses."""

    def test_returns_immediately_on_completed(self):
        """Returns as soon as job is 'completed'."""
        jobs_client = _make_jobs_client("completed")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)
        assert job.status == "completed"

    def test_returns_immediately_on_error(self):
        """Returns (without raising) when job is 'error'."""
        jobs_client = _make_jobs_client("error")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)
        assert job.status == "error"

    def test_returns_immediately_on_cancelled(self):
        """Returns when job is 'cancelled'."""
        jobs_client = _make_jobs_client("cancelled")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)
        assert job.status == "cancelled"

    def test_returns_job_object(self):
        """Returns the actual job object from get_job().data() (not a copy)."""
        expected_job = MagicMock()
        expected_job.status = "completed"
        jobs_client = MagicMock()
        jobs_client.get_job.return_value = _resp(expected_job)
        jobs_client.get_job_status.return_value = _resp(MagicMock(model_dump=MagicMock(return_value={})))
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)
        assert job is expected_job


# ---------------------------------------------------------------------------
# status_to_check behaviour
# ---------------------------------------------------------------------------


class TestWaitForPlatformJobStatusToCheck:
    """Tests that status_to_check stops the loop at a non-terminal status."""

    def test_stops_on_status_to_check(self):
        """Returns when the job reaches status_to_check before terminal."""
        jobs_client = _make_jobs_client("created", "pending", "active")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0, status_to_check="active")
        assert job.status == "active"

    def test_also_stops_on_terminal_when_status_to_check_set(self):
        """If job reaches a terminal status before status_to_check, still returns."""
        jobs_client = _make_jobs_client("created", "error")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0, status_to_check="active")
        assert job.status == "error"

    def test_terminal_set_includes_status_to_check(self):
        """poll_until_terminal is called with status_to_check merged into terminal set."""
        jobs_client = _make_jobs_client("paused")
        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal") as mock_poll:
            # Simulate poll_until_terminal calling get_status once
            def fake_poll(get_status, label, terminal, timeout, image_pull_timeout, poll_interval):
                get_status()

            mock_poll.side_effect = fake_poll
            wait_for_platform_job(_make_sdk(), "my-job", "ws", status_to_check="paused")

        _, kwargs = mock_poll.call_args
        terminal_used = mock_poll.call_args[1]["terminal"] if mock_poll.call_args[1] else mock_poll.call_args[0][2]
        assert "paused" in terminal_used
        for ts in TERMINAL_STATUSES:
            assert ts in terminal_used


# ---------------------------------------------------------------------------
# image_pull_timeout behaviour
# ---------------------------------------------------------------------------


class TestWaitForPlatformJobImagePullTimeout:
    """Tests that pending time is handled by poll_until_terminal's image_pull_timeout."""

    def test_pending_status_does_not_consume_main_timeout(self):
        """A job stuck in pending does not exhaust the execution timeout."""
        # pending -> completed: pending time should NOT count against timeout=5.0
        jobs_client = _make_jobs_client("pending", "completed")
        with _patch_client(jobs_client):
            job = wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0, image_pull_timeout=60.0)
        assert job.status == "completed"

    def test_image_pull_timeout_parameter_passed_to_poll_until_terminal(self):
        """image_pull_timeout is forwarded to poll_until_terminal."""
        jobs_client = _make_jobs_client("completed")
        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal") as mock_poll:

            def fake_poll(get_status, label, terminal, timeout, image_pull_timeout, poll_interval):
                get_status()

            mock_poll.side_effect = fake_poll
            wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=30.0, image_pull_timeout=999.0)

        args = mock_poll.call_args
        # image_pull_timeout may be positional or keyword
        if args[1]:
            assert args[1]["image_pull_timeout"] == 999.0
        else:
            assert args[0][4] == 999.0

    def test_default_image_pull_timeout_is_600(self):
        """Default image_pull_timeout is 600 seconds."""
        jobs_client = _make_jobs_client("completed")
        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal") as mock_poll:

            def fake_poll(get_status, label, terminal, timeout, image_pull_timeout, poll_interval):
                get_status()

            mock_poll.side_effect = fake_poll
            wait_for_platform_job(_make_sdk(), "my-job", "ws")

        args = mock_poll.call_args
        if args[1]:
            assert args[1]["image_pull_timeout"] == 600.0
        else:
            assert args[0][4] == 600.0


# ---------------------------------------------------------------------------
# Timeout error enrichment
# ---------------------------------------------------------------------------


class TestWaitForPlatformJobTimeoutError:
    """Tests that TimeoutError from poll_until_terminal is enriched with context."""

    def test_raises_timeout_error_when_poll_times_out(self):
        """TimeoutError propagates when poll_until_terminal raises it."""
        jobs_client = _make_jobs_client("created")
        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal") as mock_poll:
            mock_poll.side_effect = TimeoutError("'my-job' timed out after 5.0s. Status: created")
            with pytest.raises(TimeoutError):
                wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)

    def test_timeout_error_includes_status_history(self):
        """TimeoutError message includes the accumulated status history."""
        jobs_client = _make_jobs_client("created", "pending")

        def fake_poll(get_status, label, terminal, timeout, image_pull_timeout, poll_interval):
            # Call get_status twice to populate history, then timeout
            get_status()
            get_status()
            raise TimeoutError(f"'{label}' timed out after {timeout}s. Status: pending")

        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal", side_effect=fake_poll):
            with pytest.raises(TimeoutError) as exc_info:
                wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)

        assert "Status history:" in str(exc_info.value)
        assert "created" in str(exc_info.value)
        assert "pending" in str(exc_info.value)

    def test_timeout_error_includes_job_status_details(self):
        """TimeoutError message includes detailed job status from get_job_status API."""
        jobs_client = _make_jobs_client("pending")
        jobs_client.get_job_status.return_value = _resp(
            MagicMock(model_dump=MagicMock(return_value={"status": "pending", "message": "pulling image"}))
        )

        def fake_poll(get_status, label, terminal, timeout, image_pull_timeout, poll_interval):
            get_status()
            raise TimeoutError(f"'{label}' timed out")

        with _patch_client(jobs_client), patch("nmp.testing.e2e.jobs.poll_until_terminal", side_effect=fake_poll):
            with pytest.raises(TimeoutError) as exc_info:
                wait_for_platform_job(_make_sdk(), "my-job", "ws", timeout=5.0)

        assert "Job status details:" in str(exc_info.value)
