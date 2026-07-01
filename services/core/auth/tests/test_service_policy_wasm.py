# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nmp.common.config import Configuration
from nmp.core.auth.config import AuthServiceConfig
from nmp.core.auth.service import AuthService


@pytest.fixture(autouse=True)
def clear_config_overrides():
    yield
    Configuration.clear_override(AuthServiceConfig)


@pytest.mark.asyncio
async def test_on_startup_preflights_embedded_policy_wasm(monkeypatch: pytest.MonkeyPatch):
    calls: list[bool] = []
    Configuration.set_override(
        AuthServiceConfig(
            enabled=True,
            policy_decision_point_provider="embedded",
            embedded_pdp_auto_build_wasm=False,
        )
    )
    monkeypatch.setattr(
        "nmp.core.auth.service.ensure_embedded_policy_wasm", lambda *, auto_build: calls.append(auto_build)
    )

    await AuthService().on_startup()

    assert calls == [False]


@pytest.mark.parametrize(
    "config",
    [
        AuthServiceConfig(enabled=False, policy_decision_point_provider="embedded"),
        AuthServiceConfig(enabled=True, policy_decision_point_provider="opa"),
    ],
)
@pytest.mark.asyncio
async def test_on_startup_skips_policy_wasm_preflight_when_not_needed(
    config: AuthServiceConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[bool] = []
    Configuration.set_override(config)
    monkeypatch.setattr(
        "nmp.core.auth.service.ensure_embedded_policy_wasm", lambda *, auto_build: calls.append(auto_build)
    )

    await AuthService().on_startup()

    assert calls == []
