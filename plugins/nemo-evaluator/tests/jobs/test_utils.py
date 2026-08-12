# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for evaluator job helpers."""

from __future__ import annotations

from nemo_evaluator.jobs.utils import run_with_isolated_async_sdk
from pytest_mock import MockerFixture


def test_run_with_isolated_async_sdk_passes_cloned_client(mocker: MockerFixture) -> None:
    cloned = mocker.Mock(name="cloned_sdk")
    async_sdk = mocker.Mock(name="async_sdk")
    async_sdk.copy.return_value = cloned
    http_client = mocker.AsyncMock(name="http_client")
    http_client.__aenter__.return_value = http_client
    http_client.__aexit__.return_value = None
    mocker.patch("nemo_evaluator.jobs.utils.DefaultAsyncHttpxClient", return_value=http_client)

    seen: list[object] = []

    async def fn(sdk: object) -> int:
        seen.append(sdk)
        return 42

    assert run_with_isolated_async_sdk(async_sdk, fn) == 42
    async_sdk.copy.assert_called_once_with(http_client=http_client)
    assert seen == [cloned]
