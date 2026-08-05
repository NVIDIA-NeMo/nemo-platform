# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from nemo_platform import APIConnectionError, APIStatusError, AuthenticationError
from nemo_platform_ext.cli.core import waiters

WAITERS_MODULE = "nemo_platform_ext.cli.core.waiters"


class _DummyLive:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> _DummyLive:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def update(self, *args: object) -> None:
        pass

    def stop(self) -> None:
        pass

    def start(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _quiet_rich_output() -> Iterator[None]:
    with (
        patch(f"{WAITERS_MODULE}.Live", _DummyLive),
        patch(f"{WAITERS_MODULE}.console.print"),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_telemetry() -> Iterator[None]:
    """Neutralize best-effort job_run telemetry so waiter tests never do real I/O."""
    with patch("nemo_platform_ext.cli.telemetry.emit.emit_event"):
        yield


@pytest.fixture
def frozen_time() -> Iterator[MagicMock]:
    with patch(f"{WAITERS_MODULE}.time.time", return_value=0) as time:
        yield time


@pytest.fixture
def waiter_pause() -> Iterator[MagicMock]:
    with patch(f"{WAITERS_MODULE}._pause") as pause:
        yield pause


@pytest.fixture
def gateway_wait() -> Iterator[MagicMock]:
    with patch(f"{WAITERS_MODULE}.wait_for_gateway", return_value=True) as wait_for_gateway:
        yield wait_for_gateway


def test_wait_for_platform_job_returns_true_on_completed(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="completed")

    assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is True

    jobs.get_status.assert_called_once_with("job-a", workspace="default")
    frozen_time.assert_called()


def test_wait_for_platform_job_returns_false_on_error(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="error")

    assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is False
    frozen_time.assert_called()


def test_wait_for_inference_deployment_uses_remaining_timeout_for_gateway(gateway_wait: MagicMock) -> None:
    client = MagicMock()
    client.inference.deployments.retrieve.return_value = SimpleNamespace(
        status="READY",
        status_message="",
        status_history=[],
    )

    with patch(f"{WAITERS_MODULE}.time.time", side_effect=[100.0, 104.0, 104.0, 104.0]):
        assert waiters.wait_for_inference_deployment(
            client,
            "deployment-a",
            workspace="default",
            timeout=10,
            poll_interval=2,
        )

    gateway_wait.assert_called_once()
    assert gateway_wait.call_args.args[:3] == (client, "deployment-a", "default")
    assert gateway_wait.call_args.kwargs["timeout"] == pytest.approx(6.0)
    assert gateway_wait.call_args.kwargs["poll_interval"] == 2


def test_wait_for_inference_deployment_uses_model_provider_id_for_gateway(gateway_wait: MagicMock) -> None:
    client = MagicMock()
    client.inference.deployments.retrieve.return_value = SimpleNamespace(
        status="READY",
        status_message="",
        status_history=[],
        model_provider_id="provider-workspace/generated-provider",
    )

    with patch(f"{WAITERS_MODULE}.time.time", side_effect=[100.0, 104.0, 104.0, 104.0]):
        assert waiters.wait_for_inference_deployment(
            client,
            "deployment-a",
            workspace="default",
            timeout=10,
            poll_interval=2,
        )

    assert gateway_wait.call_args.args[:3] == (client, "generated-provider", "provider-workspace")


def test_wait_for_inference_deployment_retries_transient_status_error(
    frozen_time: MagicMock, waiter_pause: MagicMock, gateway_wait: MagicMock
) -> None:
    client = MagicMock()
    client.inference.deployments.retrieve.side_effect = [
        APIConnectionError(request=httpx.Request("GET", "http://test")),
        SimpleNamespace(
            status="READY",
            status_message="",
            status_history=[],
        ),
    ]

    assert waiters.wait_for_inference_deployment(
        client,
        "deployment-a",
        workspace="default",
        timeout=10,
        poll_interval=1,
    )

    frozen_time.assert_called()
    waiter_pause.assert_called_once_with(1)
    gateway_wait.assert_called_once()


def test_wait_for_inference_deployment_returns_false_on_error_status(frozen_time: MagicMock) -> None:
    client = MagicMock()
    client.inference.deployments.retrieve.return_value = SimpleNamespace(
        status="ERROR",
        status_message="boom",
        status_history=[],
    )

    assert (
        waiters.wait_for_inference_deployment(
            client,
            "deployment-a",
            workspace="default",
            timeout=10,
            poll_interval=2,
        )
        is False
    )
    frozen_time.assert_called()


def test_wait_for_inference_deployment_does_not_sleep_past_timeout(waiter_pause: MagicMock) -> None:
    client = MagicMock()
    client.inference.deployments.retrieve.return_value = SimpleNamespace(
        status="PENDING",
        status_message="",
        status_history=[],
    )

    with (
        patch(f"{WAITERS_MODULE}.time.time", side_effect=[0.0, 0.0, 0.0, 4.0, 5.0, 5.0]),
    ):
        assert (
            waiters.wait_for_inference_deployment(
                client,
                "deployment-a",
                workspace="default",
                timeout=5,
                poll_interval=10,
                check_gateway=False,
            )
            is False
        )

    waiter_pause.assert_called_once_with(1.0)


def test_wait_for_platform_job_does_not_sleep_past_timeout(waiter_pause: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="running")

    with patch(f"{WAITERS_MODULE}.time.time", side_effect=[0.0, 0.0, 0.0, 4.0, 5.0, 5.0]):
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", timeout=5, poll_interval=10) is False

    waiter_pause.assert_called_once_with(1.0)


def test_wait_for_platform_job_retries_transient_status_error(frozen_time: MagicMock, waiter_pause: MagicMock) -> None:
    jobs = MagicMock()
    request = httpx.Request("GET", "http://test")
    response = httpx.Response(503, request=request)
    jobs.get_status.side_effect = [
        APIStatusError("service unavailable", response=response, body=None),
        SimpleNamespace(status="completed"),
    ]

    assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", timeout=10, poll_interval=1) is True

    frozen_time.assert_called()
    waiter_pause.assert_called_once_with(1)


def test_wait_for_gateway_does_not_sleep_past_timeout(waiter_pause: MagicMock) -> None:
    client = MagicMock()
    client.inference.gateway.provider.ready.side_effect = APIConnectionError(
        request=httpx.Request("GET", "http://test")
    )

    with patch(f"{WAITERS_MODULE}.time.time", side_effect=[0.0, 0.0, 0.0, 4.0, 5.0, 5.0]):
        assert (
            waiters.wait_for_gateway(
                client,
                "provider-a",
                workspace="default",
                timeout=5,
                poll_interval=10,
            )
            is False
        )

    waiter_pause.assert_called_once_with(1.0)


def test_wait_for_gateway_returns_false_on_non_transient_status_error(frozen_time: MagicMock) -> None:
    client = MagicMock()
    request = httpx.Request("GET", "http://test")
    response = httpx.Response(401, request=request)
    client.inference.gateway.provider.ready.side_effect = AuthenticationError(
        "unauthorized",
        response=response,
        body=None,
    )

    assert waiters.wait_for_gateway(client, "provider-a", workspace="default") is False
    frozen_time.assert_called()


def test_wait_for_gateway_reraises_unexpected_errors(frozen_time: MagicMock) -> None:
    client = MagicMock()
    client.inference.gateway.provider.ready.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        waiters.wait_for_gateway(client, "provider-a", workspace="default")
    frozen_time.assert_called()


def test_sleep_until_next_poll_rejects_non_positive_poll_interval() -> None:
    with pytest.raises(ValueError, match=r"_sleep_until_next_poll.*poll_interval"):
        waiters._sleep_until_next_poll(0.0, 10.0, 0)
