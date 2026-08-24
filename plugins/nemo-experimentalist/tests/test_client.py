# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest
from nemo_experimentalist_plugin.client import make_client
from nemo_platform_plugin.client.oidc import NMPOIDCConfig

REMOTE_URL = "https://nemo-platform.example.com"


def test_no_base_url_uses_active_context() -> None:
    with (
        patch("nemo_experimentalist_plugin.client.discover_nmp_config") as discover,
        patch("nemo_experimentalist_plugin.client.AsyncNemoClient") as client_cls,
    ):
        client = make_client(None)

    discover.assert_not_called()
    client_cls.assert_called_once_with()
    assert client is client_cls.return_value


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "0.0.0.0"])
def test_loopback_uses_direct_mode_without_auth_discovery(host: str) -> None:
    config_path = MagicMock()
    config_path.exists.return_value = True
    base_url = f"http://[{host}]:8080" if host == "::1" else f"http://{host}:8080"

    with (
        patch("nemo_experimentalist_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch("nemo_experimentalist_plugin.client.discover_nmp_config") as discover,
        patch("nemo_experimentalist_plugin.client.AsyncNemoClient") as client_cls,
    ):
        client = make_client(base_url)

    discover.assert_not_called()
    client_cls.assert_called_once_with(base_url=base_url)
    assert client is client_cls.return_value


def test_remote_without_local_config_uses_direct_mode_without_auth_discovery() -> None:
    config_path = MagicMock()
    config_path.exists.return_value = False

    with (
        patch("nemo_experimentalist_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch("nemo_experimentalist_plugin.client.discover_nmp_config") as discover,
        patch("nemo_experimentalist_plugin.client.AsyncNemoClient") as client_cls,
    ):
        client = make_client(REMOTE_URL)

    discover.assert_not_called()
    client_cls.assert_called_once_with(base_url=REMOTE_URL)
    assert client is client_cls.return_value


def test_remote_no_auth_ignores_unrelated_local_oauth_context() -> None:
    config_path = MagicMock()
    config_path.exists.return_value = True

    with (
        patch("nemo_experimentalist_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch(
            "nemo_experimentalist_plugin.client.discover_nmp_config",
            return_value=NMPOIDCConfig(auth_enabled=False),
        ) as discover,
        patch("nemo_experimentalist_plugin.client.AsyncNemoClient") as client_cls,
    ):
        client = make_client(REMOTE_URL)

    discover.assert_called_once_with(REMOTE_URL)
    client_cls.assert_called_once_with(base_url=REMOTE_URL)
    assert client is client_cls.return_value


def test_remote_auth_uses_local_oauth_context() -> None:
    config_path = MagicMock()
    config_path.exists.return_value = True

    with (
        patch("nemo_experimentalist_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch(
            "nemo_experimentalist_plugin.client.discover_nmp_config",
            return_value=NMPOIDCConfig(
                auth_enabled=True,
                client_id="nemo-cli",
                token_endpoint="https://auth.example.com/token",
            ),
        ) as discover,
        patch("nemo_experimentalist_plugin.client.AsyncNemoClient") as client_cls,
    ):
        client = make_client(REMOTE_URL)

    discover.assert_called_once_with(REMOTE_URL)
    client_cls.assert_called_once_with(base_url=REMOTE_URL, config_path=config_path)
    assert client is client_cls.return_value
