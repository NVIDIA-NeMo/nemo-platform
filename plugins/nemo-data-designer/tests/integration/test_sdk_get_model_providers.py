# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pytest

pytestmark = pytest.mark.integration


def test_get_default_model_providers_returns_registered_providers() -> None:
    """The SDK exposes IGW-registered providers as Data Designer ModelProviders."""

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = u.make_dd_client(client_context)
        providers = dd_client.get_default_model_providers()

    provider_names = {provider.name for provider in providers}
    assert u.OPEN_PROVIDER_NAME in {name.split("/")[-1] for name in provider_names}
    assert u.RESTRICTED_PROVIDER_NAME in {name.split("/")[-1] for name in provider_names}
    for provider in providers:
        assert isinstance(provider, dd.ModelProvider)
        assert provider.endpoint, f"Provider {provider.name!r} has no endpoint"


def test_get_default_model_providers_returns_empty_list_when_none_registered() -> None:
    """No registered providers means the SDK returns an empty list (not None, not an error)."""

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        providers = dd_client.get_default_model_providers()

    assert providers == []
