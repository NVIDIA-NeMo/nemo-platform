# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for restart policy → docker run kwargs."""

from __future__ import annotations

import pytest
from nemo_deployments_plugin.backends.docker.containers import restart_policy_kwargs


@pytest.mark.parametrize(
    ("policy", "backoff", "expected"),
    [
        ("Always", 6, {"restart_policy": {"Name": "always"}}),
        ("OnFailure", 3, {"restart_policy": {"Name": "on-failure", "MaximumRetryCount": 3}}),
        ("Never", 6, {}),
    ],
)
def test_restart_policy_kwargs(policy: str, backoff: int, expected: dict) -> None:
    assert restart_policy_kwargs(policy, backoff) == expected  # type: ignore[arg-type]
