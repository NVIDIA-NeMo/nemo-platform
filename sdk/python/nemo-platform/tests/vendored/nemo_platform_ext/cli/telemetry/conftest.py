# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterator

import pytest
from nemo_platform.cli.telemetry.events import _CI_ENV_VARS


@pytest.fixture(autouse=True)
def _clear_ci_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear CI markers so telemetry tests are deterministic on developer machines and in CI.

    Without this, tests that assert the default ``is_ci`` value pass locally but fail when the
    suite runs under GitHub Actions (which sets ``CI`` and ``GITHUB_ACTIONS``). Tests that
    exercise CI detection set these variables explicitly, which overrides this fixture.
    """
    for var in _CI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("NEMO_DEPLOYMENT_TYPE", raising=False)
    yield
