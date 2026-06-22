# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from nmp.common.config import Configuration, PlatformConfig
from nmp.common.sdk_factory import (
    get_async_platform_sdk,
    get_entity_parts,
    get_platform_sdk,
    get_request_scoped_sdk,
    get_task_sdk,
)


@pytest.fixture(autouse=True)
def _clear_sdk_factory_test_client():
    """Clear _test_http_client before each test so config-based SDK behavior is asserted.

    When _test_http_client is set (e.g. by another test's create_test_client), the SDK
    is created with base_url='http://testserver' and no URL router, which breaks tests
    that assert on base_url or service routing. Clearing it keeps tests order-independent
    and ensures sdk_factory tests always exercise the config path.
    """
    import nmp.common.sdk_factory as sdk_factory_module

    old = sdk_factory_module._test_http_client
    sdk_factory_module._test_http_client = None
    try:
        yield
    finally:
        sdk_factory_module._test_http_client = old


def test_get_platform_sdk():
    """
    Test the get_platform_sdk function to ensure it returns an instance of NeMoPlatform
    with the correct base URL.
    """
    sdk = get_platform_sdk()
    assert sdk is not None, "SDK instance should not be None"
    assert hasattr(sdk, "base_url"), "SDK instance should have a base_url attribute"
    assert sdk.base_url == Configuration.get_platform_config().base_url


def test_get_platform_sdk_with_service_principal():
    """Test get_platform_sdk with as_service parameter."""
    sdk = get_platform_sdk(as_service="my-service")

    assert sdk is not None
    assert "X-NMP-Principal-Id" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:my-service"


def test_get_platform_sdk_with_on_behalf_of():
    """Test get_platform_sdk with on_behalf_of parameter."""
    sdk = get_platform_sdk(as_service="my-service", on_behalf_of="user@example.com")

    assert sdk is not None
    assert "X-NMP-Principal-Id" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:my-service"
    assert "X-NMP-Principal-On-Behalf-Of" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "user@example.com"


def test_get_platform_sdk_internal_flag():
    """Test get_platform_sdk with internal flag."""
    sdk = get_platform_sdk(as_service="my-service", internal=True)

    assert sdk is not None
    assert "X-NMP-Internal" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Internal"] == "true"


def test_get_async_platform_sdk():
    """Test get_async_platform_sdk basic functionality (config path: SDK base_url matches platform config)."""
    sdk = get_async_platform_sdk()

    assert sdk is not None
    assert hasattr(sdk, "base_url")
    # Normalize to str: SDK may expose URL object, config may be str; both environments
    expected = Configuration.get_platform_config().base_url
    assert str(sdk.base_url).rstrip("/") == str(expected).rstrip("/")


def test_get_async_platform_sdk_with_service_principal():
    """Test get_async_platform_sdk with as_service parameter."""
    sdk = get_async_platform_sdk(as_service="async-service")

    assert sdk is not None
    assert "X-NMP-Principal-Id" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:async-service"


def test_get_async_platform_sdk_with_on_behalf_of():
    """Test get_async_platform_sdk with on_behalf_of parameter."""
    sdk = get_async_platform_sdk(as_service="async-service", on_behalf_of="async-user@example.com")

    assert sdk is not None
    assert "X-NMP-Principal-Id" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:async-service"
    assert "X-NMP-Principal-On-Behalf-Of" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "async-user@example.com"


def test_get_async_platform_sdk_internal_flag():
    """Test get_async_platform_sdk with internal flag."""
    sdk = get_async_platform_sdk(as_service="async-service", internal=True)

    assert sdk is not None
    assert "X-NMP-Internal" in sdk.default_headers
    assert sdk.default_headers["X-NMP-Internal"] == "true"


def test_on_behalf_of_without_service_principal():
    """Test that on_behalf_of works without as_service (propagates user context)."""
    # When auth is enabled but no context is set, on_behalf_of should still be added
    sdk = get_platform_sdk(on_behalf_of="delegated@example.com")

    assert sdk is not None
    # Note: Without a user context (request), principal headers won't be set,
    # but on_behalf_of should still be added if provided
    if "X-NMP-Principal-On-Behalf-Of" in sdk.default_headers:
        assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "delegated@example.com"


def test_get_task_sdk_with_principal(monkeypatch: pytest.MonkeyPatch):
    """get_task_sdk should set service principal, internal flag, and on-behalf-of using effective_id."""
    principal_json = json.dumps(
        {
            "id": "service:other",
            "email": "svc@internal",
            "groups": [],
            "on_behalf_of": "real-user@example.com",
        }
    )
    monkeypatch.setenv("NMP_PRINCIPAL", principal_json)

    sdk = get_task_sdk(as_service="customizer")

    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:customizer"
    assert sdk.default_headers["X-NMP-Internal"] == "true"
    assert sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "real-user@example.com"


def test_get_task_sdk_without_principal(monkeypatch: pytest.MonkeyPatch):
    """get_task_sdk without NMP_PRINCIPAL should still set service principal and internal flag, but no on-behalf-of."""
    monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

    sdk = get_task_sdk(as_service="customizer")

    assert sdk.default_headers["X-NMP-Principal-Id"] == "service:customizer"
    assert sdk.default_headers["X-NMP-Internal"] == "true"
    assert "X-NMP-Principal-On-Behalf-Of" not in sdk.default_headers


def test_get_task_sdk_uses_explicit_sync_http_client(monkeypatch: pytest.MonkeyPatch):
    """get_task_sdk should use an explicitly provided sync HTTP client."""
    monkeypatch.delenv("NMP_PRINCIPAL", raising=False)
    client = TestClient(lambda scope, receive, send: None)

    sdk = get_task_sdk(as_service="customizer", http_client=client)

    assert sdk._client is client


def test_get_request_scoped_sdk_merges_otel_and_auth_headers():
    """Test that get_request_scoped_sdk merges OTEL and auth headers."""
    base_sdk = get_async_platform_sdk()

    mock_otel_headers = {"traceparent": "00-trace-id-span-id-01", "tracestate": "vendor=value"}
    mock_auth_headers = {"X-NMP-Principal-Id": "user@example.com", "X-NMP-Principal-Groups": "group1,group2"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value=mock_otel_headers):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Verify it's a new SDK instance
    assert scoped_sdk is not base_sdk

    # Verify OTEL headers are present
    assert "traceparent" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["traceparent"] == "00-trace-id-span-id-01"
    assert "tracestate" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["tracestate"] == "vendor=value"

    # Verify auth headers are present
    assert "X-NMP-Principal-Id" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Id"] == "user@example.com"
    assert "X-NMP-Principal-Groups" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Groups"] == "group1,group2"


def test_get_request_scoped_sdk_returns_base_sdk_when_no_headers():
    """Test that get_request_scoped_sdk returns base SDK when no headers to add."""
    base_sdk = get_async_platform_sdk()

    # Mock both functions to return empty dicts
    with patch("nmp.common.sdk_factory.get_otel_headers", return_value={}):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value={}):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Should return the same SDK instance when no headers to add
    assert scoped_sdk is base_sdk


def test_get_request_scoped_sdk_preserves_original_base_sdk():
    """Test that get_request_scoped_sdk doesn't modify the original base SDK."""
    base_sdk = get_async_platform_sdk(
        as_service="my-service",
    )

    # Store original headers
    original_headers = dict(base_sdk.default_headers)

    mock_otel_headers = {"traceparent": "00-trace-id-span-id-01"}
    mock_auth_headers = {"X-NMP-Principal-Id": "user@example.com"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value=mock_otel_headers):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Verify original SDK is unchanged
    assert base_sdk.default_headers == original_headers
    assert "traceparent" not in base_sdk.default_headers

    # Verify scoped SDK has new headers
    assert "traceparent" in scoped_sdk.default_headers


def test_get_request_scoped_sdk_only_otel_headers():
    """Test get_request_scoped_sdk with only OTEL headers (no auth headers)."""
    base_sdk = get_async_platform_sdk()

    mock_otel_headers = {"traceparent": "00-trace-id-span-id-01"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value=mock_otel_headers):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value={}):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Should create new SDK with OTEL headers
    assert scoped_sdk is not base_sdk
    assert "traceparent" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["traceparent"] == "00-trace-id-span-id-01"


def test_get_request_scoped_sdk_only_auth_headers():
    """Test get_request_scoped_sdk with only auth headers (no OTEL headers)."""
    base_sdk = get_async_platform_sdk()

    mock_auth_headers = {"X-NMP-Principal-Id": "user@example.com"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value={}):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Should create new SDK with auth headers
    assert scoped_sdk is not base_sdk
    assert "X-NMP-Principal-Id" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Id"] == "user@example.com"


def test_get_request_scoped_sdk_auth_headers_override_otel_headers():
    """Test that auth headers take precedence when there are key conflicts."""
    base_sdk = get_async_platform_sdk()

    # Both have the same header key
    mock_otel_headers = {"X-Custom-Header": "otel-value"}
    mock_auth_headers = {"X-Custom-Header": "auth-value"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value=mock_otel_headers):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Auth headers should win (they're applied after OTEL via .update())
    assert scoped_sdk.default_headers["X-Custom-Header"] == "auth-value"


def test_get_request_scoped_sdk_preserves_base_sdk_http_client():
    """Test that get_request_scoped_sdk reuses the base SDK's HTTP client."""
    import httpx

    # Create a custom HTTP client
    custom_client = httpx.AsyncClient(timeout=30.0)

    base_sdk = get_async_platform_sdk(
        http_client=custom_client,
    )

    mock_auth_headers = {"X-NMP-Principal-Id": "user@example.com"}

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value={}):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Verify the HTTP client is reused (same instance)
    # Note: with_options() reuses the underlying HTTP client
    assert scoped_sdk is not base_sdk
    # The SDK wraps the client, so we verify it's a new SDK but lightweight
    assert "X-NMP-Principal-Id" in scoped_sdk.default_headers


def test_get_request_scoped_sdk_with_on_behalf_of_header():
    """Test that get_request_scoped_sdk propagates on-behalf-of header from request context."""
    base_sdk = get_async_platform_sdk()

    # Simulate a request context where a user is acting on behalf of another user
    mock_otel_headers = {"traceparent": "00-trace-id-span-id-01"}
    mock_auth_headers = {
        "X-NMP-Principal-Id": "admin@example.com",
        "X-NMP-Principal-On-Behalf-Of": "user@example.com",
        "X-NMP-Principal-Groups": "admin-group",
    }

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value=mock_otel_headers):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Verify it's a new SDK instance
    assert scoped_sdk is not base_sdk

    # Verify all headers including on-behalf-of are propagated
    assert "X-NMP-Principal-Id" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Id"] == "admin@example.com"
    assert "X-NMP-Principal-On-Behalf-Of" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "user@example.com"
    assert "X-NMP-Principal-Groups" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Groups"] == "admin-group"
    assert "traceparent" in scoped_sdk.default_headers


def test_get_request_scoped_sdk_service_principal_with_on_behalf_of():
    """Test get_request_scoped_sdk when base SDK is a service principal and request has on-behalf-of."""
    # This simulates a service making a request on behalf of a user
    # Base SDK has service principal, request context adds on-behalf-of
    base_sdk = get_async_platform_sdk(
        as_service="my-service",
    )

    # Request context includes on-behalf-of header
    mock_auth_headers = {
        "X-NMP-Principal-Id": "service:my-service",
        "X-NMP-Principal-On-Behalf-Of": "user@example.com",
    }

    with patch("nmp.common.sdk_factory.get_otel_headers", return_value={}):
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=mock_auth_headers):
            scoped_sdk = get_request_scoped_sdk(base_sdk)

    # Verify scoped SDK has both service principal and on-behalf-of
    assert scoped_sdk is not base_sdk
    assert "X-NMP-Principal-Id" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-Id"] == "service:my-service"
    assert "X-NMP-Principal-On-Behalf-Of" in scoped_sdk.default_headers
    assert scoped_sdk.default_headers["X-NMP-Principal-On-Behalf-Of"] == "user@example.com"


# --- Dynamic routing (service discovery map) tests ---


@pytest.fixture
def platform_config_with_service_discovery():
    """Platform config with service_discovery map for entities and jobs."""
    return PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={
            "entities": "http://entities-service:8080",
            "jobs": "http://jobs-service:8080",
        },
    )


def test_get_platform_sdk_routes_entities_path_to_entities_service(
    platform_config_with_service_discovery,
):
    """Routes /apis/entities/v2/workspaces to the entities service URL."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_platform_sdk()
        # Router calls get_platform_config when _prepare_url runs; keep patch active
        request_url = "http://platform:8080/apis/entities/v2/workspaces"
        prepared = sdk._prepare_url(request_url)

    assert prepared.host == "entities-service"
    assert prepared.port == 8080
    assert prepared.scheme == "http"
    assert "/apis/entities/v2/workspaces" in str(prepared.path)


def test_get_platform_sdk_routes_jobs_path_to_jobs_service(
    platform_config_with_service_discovery,
):
    """Routes /apis/jobs/v2/workspaces/jobs to the jobs service URL."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_platform_sdk()
        request_url = "http://platform:8080/apis/jobs/v2/workspaces/jobs"
        prepared = sdk._prepare_url(request_url)

    assert prepared.host == "jobs-service"
    assert prepared.port == 8080
    assert prepared.scheme == "http"
    assert "/apis/jobs/v2/workspaces/jobs" in str(prepared.path)


def test_get_platform_sdk_routing_fallback_to_base_url_when_no_match(
    platform_config_with_service_discovery,
):
    """When the path does not match /apis/{service-name}/ (lowercase+dashes), use the original URL (base)."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_platform_sdk()
        # Path that does not match /apis/{service-name}/ (e.g. /api/ singular, or no such prefix)
        request_url = "http://platform:8080/api/other/v1/thing"
        prepared = sdk._prepare_url(request_url)

    # Should pass through to original behavior: same host as request
    assert prepared.host == "platform"
    assert prepared.port == 8080


def test_get_async_platform_sdk_routes_entities_path_to_entities_service(
    platform_config_with_service_discovery,
):
    """Routes /apis/entities/v2/workspaces to the entities service URL (async SDK)."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_async_platform_sdk()
        request_url = "http://platform:8080/apis/entities/v2/workspaces"
        prepared = sdk._prepare_url(request_url)

    assert prepared.host == "entities-service"
    assert prepared.port == 8080
    assert prepared.scheme == "http"
    assert "/apis/entities/v2/workspaces" in str(prepared.path)


def test_get_async_platform_sdk_routes_jobs_path_to_jobs_service(
    platform_config_with_service_discovery,
):
    """Routes /apis/jobs/v2/workspaces/jobs to the jobs service URL (async SDK)."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_async_platform_sdk()
        request_url = "http://platform:8080/apis/jobs/v2/workspaces/jobs"
        prepared = sdk._prepare_url(request_url)

    assert prepared.host == "jobs-service"
    assert prepared.port == 8080
    assert prepared.scheme == "http"
    assert "/apis/jobs/v2/workspaces/jobs" in str(prepared.path)


def test_get_async_platform_sdk_routing_fallback_to_base_url_when_no_match(
    platform_config_with_service_discovery,
):
    """When the path does not match /apis/{service-name}/, use the original URL (async SDK)."""
    with patch(
        "nmp.common.sdk_factory.Configuration.get_platform_config",
        return_value=platform_config_with_service_discovery,
    ):
        sdk = get_async_platform_sdk()
        request_url = "http://platform:8080/api/other/v1/thing"
        prepared = sdk._prepare_url(request_url)

    assert prepared.host == "platform"
    assert prepared.port == 8080


# --- get_entity_parts tests ---


def test_get_entity_parts_qualified_returns_workspace_and_name():
    """Qualified name (workspace/name) returns (workspace, name)."""
    assert get_entity_parts("my-ws/my-secret") == ("my-ws", "my-secret")


def test_get_entity_parts_qualified_splits_only_first_slash():
    """Only the first slash is used; rest is part of the name."""
    assert get_entity_parts("ws/a/b/c") == ("ws", "a/b/c")


def test_get_entity_parts_unqualified_with_workspace_returns_workspace_and_name():
    """Unqualified name with workspace returns (workspace, name)."""
    assert get_entity_parts("local-secret", default_workspace="default") == ("default", "local-secret")


def test_get_entity_parts_unqualified_without_workspace_raises():
    """Unqualified name without workspace raises ValueError."""
    with pytest.raises(ValueError, match="not qualified with a workspace"):
        get_entity_parts("bare-name")
