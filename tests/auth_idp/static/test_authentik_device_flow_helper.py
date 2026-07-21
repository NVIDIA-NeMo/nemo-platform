# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.auth_idp.device_flow import authentik_flow_executor_url, url_origin, with_url_origin

pytestmark = [pytest.mark.auth_idp]


def test_authentik_flow_executor_url_preserves_default_login_next_query() -> None:
    assert authentik_flow_executor_url(
        "https://127.0.0.1:38080",
        "/flows/-/default/authentication/?next=/device%3Fcode%3D123456789",
    ) == (
        "https://127.0.0.1:38080/api/v3/flows/executor/default-authentication-flow/"
        "?query=next%3D%2Fdevice%253Fcode%253D123456789"
    )


def test_authentik_flow_executor_url_preserves_if_flow_query() -> None:
    assert authentik_flow_executor_url(
        "https://127.0.0.1:38080",
        "/if/flow/default-provider-authorization-implicit-consent/?code=abc&state=xyz",
    ) == (
        "https://127.0.0.1:38080/api/v3/flows/executor/default-provider-authorization-implicit-consent/"
        "?query=code%3Dabc%26state%3Dxyz"
    )


def test_authentik_flow_executor_url_ignores_non_flow_browser_urls() -> None:
    assert authentik_flow_executor_url("https://127.0.0.1:38080", "/device?code=123456789") is None


def test_url_origin_keeps_runtime_port_forward_separate_from_advertised_device_origin() -> None:
    assert url_origin("https://127.0.0.1:18080/application/o/device/") == "https://127.0.0.1:18080"


def test_with_url_origin_preserves_advertised_oidc_path_for_runtime_port_forward() -> None:
    assert (
        with_url_origin(
            "https://127.0.0.1:18080/application/o/device/?x=1",
            "https://127.0.0.1:65490",
        )
        == "https://127.0.0.1:65490/application/o/device/?x=1"
    )
