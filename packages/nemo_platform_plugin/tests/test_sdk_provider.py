# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`nemo_platform_plugin.sdk_provider`."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.sdk_provider import (
    DefaultSDKProvider,
    SDKProvider,
    _on_behalf_of_headers,
    _read_principal_from_env,
    get_task_sdk,
    set_sdk_provider,
)

# ---------------------------------------------------------------------------
# _read_principal_from_env
# ---------------------------------------------------------------------------


class TestReadPrincipalFromEnv:
    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)
        assert _read_principal_from_env() is None

    def test_returns_none_when_empty(self, monkeypatch):
        monkeypatch.setenv("NMP_PRINCIPAL", "")
        assert _read_principal_from_env() is None

    def test_returns_none_when_id_missing(self, monkeypatch):
        monkeypatch.setenv("NMP_PRINCIPAL", json.dumps({"email": "a@b.com"}))
        assert _read_principal_from_env() is None

    def test_returns_none_when_id_empty(self, monkeypatch):
        monkeypatch.setenv("NMP_PRINCIPAL", json.dumps({"id": ""}))
        assert _read_principal_from_env() is None

    def test_parses_valid_principal(self, monkeypatch):
        principal = {"id": "user@example.com", "email": "user@example.com", "groups": ["team-a"]}
        monkeypatch.setenv("NMP_PRINCIPAL", json.dumps(principal))
        result = _read_principal_from_env()
        assert result == principal

    def test_raises_on_malformed_json(self, monkeypatch):
        monkeypatch.setenv("NMP_PRINCIPAL", "not-json")
        with pytest.raises(ValueError, match="Invalid JSON"):
            _read_principal_from_env()


# ---------------------------------------------------------------------------
# _on_behalf_of_headers
# ---------------------------------------------------------------------------


class TestOnBehalfOfHeaders:
    def test_simple_principal(self):
        headers = _on_behalf_of_headers({"id": "user@ex.com", "email": "user@ex.com", "groups": ["g1", "g2"]})
        assert headers["X-NMP-Principal-On-Behalf-Of"] == "user@ex.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Email"] == "user@ex.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Groups"] == "g1,g2"

    def test_delegated_principal_uses_effective(self):
        principal = {
            "id": "service:evaluator",
            "on_behalf_of": "real-user@ex.com",
            "on_behalf_of_email": "real-user@ex.com",
            "on_behalf_of_groups": ["admin"],
        }
        headers = _on_behalf_of_headers(principal)
        assert headers["X-NMP-Principal-On-Behalf-Of"] == "real-user@ex.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Email"] == "real-user@ex.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Groups"] == "admin"

    def test_no_email_or_groups(self):
        headers = _on_behalf_of_headers({"id": "user@ex.com"})
        assert headers == {"X-NMP-Principal-On-Behalf-Of": "user@ex.com"}


# ---------------------------------------------------------------------------
# DefaultSDKProvider
# ---------------------------------------------------------------------------


class TestDefaultSDKProvider:
    def test_get_task_sdk_with_principal(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://test:9090")
        monkeypatch.setenv(
            "NMP_PRINCIPAL",
            json.dumps({"id": "creator@ex.com", "email": "creator@ex.com", "groups": ["team"]}),
        )

        provider = DefaultSDKProvider()
        sdk = provider.get_task_sdk("evaluator")

        assert isinstance(sdk, NeMoPlatform)
        assert sdk.base_url == "http://test:9090"
        assert sdk.default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert sdk.default_headers["X-NMP-Internal"] == "true"
        assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "creator@ex.com"

    def test_get_task_sdk_without_principal(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://test:9090")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        provider = DefaultSDKProvider()
        sdk = provider.get_task_sdk("evaluator")

        assert sdk.default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert "X-NMP-Principal-On-Behalf-Of" not in sdk.default_headers

    def test_get_task_sdk_default_base_url(self, monkeypatch):
        monkeypatch.delenv("NMP_BASE_URL", raising=False)
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        provider = DefaultSDKProvider()
        sdk = provider.get_task_sdk("test")
        assert sdk.base_url == "http://localhost:8080"

    def test_get_platform_sdk_as_service(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://test:9090")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        provider = DefaultSDKProvider()
        sdk = provider.get_platform_sdk(as_service="my-svc", internal=True)

        assert sdk.default_headers["X-NMP-Principal-Id"] == "service:my-svc"
        assert sdk.default_headers["X-NMP-Internal"] == "true"

    def test_get_platform_sdk_on_behalf_of(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://test:9090")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        provider = DefaultSDKProvider()
        sdk = provider.get_platform_sdk(as_service="svc", on_behalf_of="user@ex.com")

        assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "user@ex.com"


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


class _CustomProvider:
    def get_task_sdk(self, service_name: str) -> NeMoPlatform:
        return NeMoPlatform(base_url="http://custom:1234")

    def get_platform_sdk(self, **kwargs) -> NeMoPlatform:
        return NeMoPlatform(base_url="http://custom:1234")


class TestProviderResolution:
    def setup_method(self):
        # Reset global state before each test.
        set_sdk_provider(None)

    def teardown_method(self):
        set_sdk_provider(None)

    def test_explicit_provider_takes_precedence(self, monkeypatch):
        monkeypatch.delenv("NMP_BASE_URL", raising=False)
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        set_sdk_provider(_CustomProvider())
        sdk = get_task_sdk("test")
        assert sdk.base_url == "http://custom:1234"

    def test_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://fallback:8080")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        # No explicit provider, no entry-points → default
        with patch("nemo_platform_plugin.sdk_provider.entry_points", return_value=[]):
            sdk = get_task_sdk("test")
        assert sdk.base_url == "http://fallback:8080"

    def test_set_none_clears_and_re_resolves(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://re-resolved:8080")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        set_sdk_provider(_CustomProvider())
        assert get_task_sdk("x").base_url == "http://custom:1234"

        # Clear the override
        set_sdk_provider(None)
        with patch("nemo_platform_plugin.sdk_provider.entry_points", return_value=[]):
            sdk = get_task_sdk("x")
        assert sdk.base_url == "http://re-resolved:8080"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_default_provider_is_protocol_instance(self):
        assert isinstance(DefaultSDKProvider(), SDKProvider)
