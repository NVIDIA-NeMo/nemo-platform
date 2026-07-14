# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

from nemo_insights_plugin.client import make_client
from nemo_platform.auth.helpers import NMPOIDCConfig

REMOTE_URL = "https://nemo-platform.example.com"


def test_remote_no_auth_ignores_unrelated_local_oauth_context() -> None:
    config_path = MagicMock()
    config_path.exists.return_value = True

    with (
        patch("nemo_insights_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch(
            "nemo_insights_plugin.client.discover_nmp_config",
            return_value=NMPOIDCConfig(auth_enabled=False),
        ),
        patch("nemo_insights_plugin.client.AsyncNeMoPlatform") as client_cls,
    ):
        client = make_client(REMOTE_URL)

    client_cls.assert_called_once_with(base_url=REMOTE_URL)
    assert client is client_cls.return_value


def test_remote_auth_uses_local_oauth_context() -> None:
    config_path = MagicMock()
    config_path.exists.return_value = True

    with (
        patch("nemo_insights_plugin.client.Config.get_default_config_path", return_value=config_path),
        patch(
            "nemo_insights_plugin.client.discover_nmp_config",
            return_value=NMPOIDCConfig(
                auth_enabled=True,
                client_id="nemo-cli",
                token_endpoint="https://auth.example.com/token",
            ),
        ),
        patch("nemo_insights_plugin.client.AsyncNeMoPlatform") as client_cls,
    ):
        client = make_client(REMOTE_URL)

    client_cls.assert_called_once_with(base_url=REMOTE_URL, config_path=config_path)
    assert client is client_cls.return_value
