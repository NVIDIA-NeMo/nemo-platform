# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from nemo_platform_ext.auth.helpers import decode_jwt_claims, generate_unsigned_jwt
from nemo_platform_ext.cli.app import app
from typer.testing import CliRunner

from ..utils import assert_exit_code

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


def _mock_oidc_config() -> SimpleNamespace:
    return SimpleNamespace(
        auth_enabled=True,
        issuer="https://idp.example.com",
        client_id="test-client",
        token_endpoint="https://idp.example.com/token",
        device_authorization_endpoint="https://idp.example.com/device",
        default_scopes="openid profile email offline_access",
        scope_prefix="api://nmp",
    )


def _discover_auth_enabled(url: str, timeout: float = 10.0) -> SimpleNamespace:
    return SimpleNamespace(auth_enabled=True)


def _discover_auth_disabled(url: str, timeout: float = 10.0) -> SimpleNamespace:
    return SimpleNamespace(auth_enabled=False)


def _discover_oidc_config(url: str, timeout: float = 10.0) -> SimpleNamespace:
    return _mock_oidc_config()


def _discover_no_oidc(url: str, timeout: float = 10.0) -> SimpleNamespace:
    return SimpleNamespace(
        auth_enabled=True,
        issuer=None,
        client_id=None,
        token_endpoint=None,
        device_authorization_endpoint=None,
    )


def _decode_jwt_noop(token: str) -> dict:
    return {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oauth_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_data = {
        "current_context": "default",
        "clusters": [
            {"name": "default", "base_url": "https://default.example.com"},
            {"name": "foo", "base_url": "https://foo.example.com"},
        ],
        "users": [
            {
                "type": "oauth",
                "name": "default",
                "token": "default-token",
                "refresh_token": "default-refresh",
            },
            {
                "type": "oauth",
                "name": "foo",
                "token": "foo-token",
                "refresh_token": "foo-refresh",
            },
        ],
        "contexts": [
            {
                "name": "default",
                "cluster": "default",
                "user": "default",
                "workspace": "default-workspace",
            },
            {
                "name": "foo",
                "cluster": "foo",
                "user": "foo",
                "workspace": "foo-workspace",
            },
        ],
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.safe_dump(config_data, f)
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config_path))
    return config_path


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


def test_auth_logout_writes_to_selected_context(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_enabled)
    with patch("nemo_platform_ext.config.config.Config.write") as mock_write:
        result = runner.invoke(app, ["--context", "foo", "auth", "logout"])

    assert_exit_code(result, 0)
    assert mock_write.call_count == 1
    assert mock_write.call_args.kwargs["context_name"] == "foo"


def test_auth_logout_clears_selected_context_credentials(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_enabled)

    result = runner.invoke(app, ["--context", "foo", "auth", "logout"])

    assert_exit_code(result, 0)
    assert "Logged out successfully" in result.output

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    default_user = next(user for user in data["users"] if user["name"] == "default")
    foo_user = next(user for user in data["users"] if user["name"] == "foo")

    assert default_user["type"] == "oauth"
    assert default_user["token"] == "default-token"
    assert default_user["refresh_token"] == "default-refresh"
    assert foo_user["type"] == "no-auth"
    assert "token" not in foo_user
    assert "refresh_token" not in foo_user


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_auth_refresh_updates_selected_context_only(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    class FakeTokenProvider:
        def __init__(self, *args, **kwargs):
            self.tokens = SimpleNamespace(
                access_token="foo-refreshed-token",
                refresh_token="foo-refreshed-refresh",
            )

        def force_refresh(self) -> None:
            return None

    def discover_refresh_config(url: str, timeout: float = 10.0) -> SimpleNamespace:
        return SimpleNamespace(
            client_id="test-client-id",
            token_endpoint="https://idp.example.com/token",
            default_scopes="openid profile email",
            scope_prefix=None,
        )

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", discover_refresh_config)
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.OIDCTokenProvider", FakeTokenProvider)

    result = runner.invoke(app, ["--context", "foo", "auth", "refresh"])

    assert_exit_code(result, 0)

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    default_user = next(user for user in data["users"] if user["name"] == "default")
    foo_user = next(user for user in data["users"] if user["name"] == "foo")

    assert default_user["token"] == "default-token"
    assert default_user["refresh_token"] == "default-refresh"
    assert foo_user["token"] == "foo-refreshed-token"
    assert foo_user["refresh_token"] == "foo-refreshed-refresh"


def test_auth_refresh_regenerates_unsigned_token(oauth_config_file: Path) -> None:
    original_token = generate_unsigned_jwt(
        principal_id="admin@example.com",
        email="admin@example.com",
        groups=["platform-admin"],
        scopes=["platform:read", "platform:write"],
        expires_in_seconds=900,
        issued_at=1700000000,
        issuer="https://quickstart.local",
        extra_claims={"custom": "value"},
    )

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    foo_user = next(user for user in data["users"] if user["name"] == "foo")
    foo_user["token"] = original_token
    foo_user["refresh_token"] = None

    with open(oauth_config_file, "w") as f:
        yaml.safe_dump(data, f)

    result = runner.invoke(app, ["--context", "foo", "auth", "refresh"])

    assert_exit_code(result, 0)
    assert "Unsigned token refreshed successfully" in result.output

    with open(oauth_config_file) as f:
        refreshed_data = yaml.safe_load(f)

    refreshed_user = next(user for user in refreshed_data["users"] if user["name"] == "foo")
    refreshed_claims = decode_jwt_claims(refreshed_user["token"])

    assert refreshed_claims["sub"] == "admin@example.com"
    assert refreshed_claims["email"] == "admin@example.com"
    assert refreshed_claims["groups"] == ["platform-admin"]
    assert refreshed_claims["scope"] == "platform:read platform:write"
    assert refreshed_claims["iss"] == "https://quickstart.local"
    assert refreshed_claims["custom"] == "value"
    assert refreshed_claims["exp"] - refreshed_claims["iat"] == 900
    assert refreshed_claims["iat"] > 1700000000
    assert refreshed_user.get("refresh_token") is None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_auth_status_shows_warning_for_unsigned_token(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_enabled)
    unsigned_token = generate_unsigned_jwt(
        principal_id="admin@example.com",
        email="admin@example.com",
        expires_in_seconds=900,
        issued_at=1700000000,
    )

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    foo_user = next(user for user in data["users"] if user["name"] == "foo")
    foo_user["token"] = unsigned_token
    foo_user["refresh_token"] = None

    with open(oauth_config_file, "w") as f:
        yaml.safe_dump(data, f)

    result = runner.invoke(app, ["--context", "foo", "auth", "status"])

    assert_exit_code(result, 0)
    assert "Unsigned JWT (alg=none)" in result.output
    assert "local/testing" in result.output


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def test_auth_login_with_base_url_updates_selected_context(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    def password_grant(**kwargs) -> SimpleNamespace:
        return SimpleNamespace(token_for_nmp="foo-access-token", refresh_token="foo-refresh-token")

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_oidc_config)
    monkeypatch.setattr("nemo_platform_ext.auth.device_flow.authenticate_with_password_grant", password_grant)
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.decode_jwt_claims", _decode_jwt_noop)

    result = runner.invoke(
        app,
        [
            "--context",
            "foo",
            "auth",
            "login",
            "--base-url",
            "https://foo-updated.example.com",
            "--username",
            "user",
            "--password",
            "secret",
        ],
    )

    assert_exit_code(result, 0)

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    default_cluster = next(cluster for cluster in data["clusters"] if cluster["name"] == "default")
    foo_cluster = next(cluster for cluster in data["clusters"] if cluster["name"] == "foo")
    foo_user = next(user for user in data["users"] if user["name"] == "foo")

    assert data["current_context"] == "foo"
    assert default_cluster["base_url"].rstrip("/") == "https://default.example.com"
    assert foo_cluster["base_url"].rstrip("/") == "https://foo-updated.example.com"
    assert foo_user["token"] == "foo-access-token"
    assert foo_user["refresh_token"] == "foo-refresh-token"


def test_auth_login_context_flag_updates_selected_context(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    def password_grant(**kwargs) -> SimpleNamespace:
        return SimpleNamespace(token_for_nmp="foo-access-token", refresh_token="foo-refresh-token")

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_oidc_config)
    monkeypatch.setattr("nemo_platform_ext.auth.device_flow.authenticate_with_password_grant", password_grant)
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.decode_jwt_claims", _decode_jwt_noop)

    result = runner.invoke(
        app,
        [
            "auth",
            "login",
            "--context",
            "foo",
            "--base-url",
            "https://foo-updated.example.com",
            "--username",
            "user",
            "--password",
            "secret",
        ],
    )

    assert_exit_code(result, 0)

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    default_cluster = next(cluster for cluster in data["clusters"] if cluster["name"] == "default")
    foo_cluster = next(cluster for cluster in data["clusters"] if cluster["name"] == "foo")
    foo_user = next(user for user in data["users"] if user["name"] == "foo")

    assert data["current_context"] == "foo"
    assert default_cluster["base_url"].rstrip("/") == "https://default.example.com"
    assert foo_cluster["base_url"].rstrip("/") == "https://foo-updated.example.com"
    assert foo_user["token"] == "foo-access-token"
    assert foo_user["refresh_token"] == "foo-refresh-token"


def test_auth_login_with_base_url_creates_selected_context(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    def password_grant(**kwargs) -> SimpleNamespace:
        return SimpleNamespace(token_for_nmp="dev-access-token", refresh_token="dev-refresh-token")

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_oidc_config)
    monkeypatch.setattr("nemo_platform_ext.auth.device_flow.authenticate_with_password_grant", password_grant)
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.decode_jwt_claims", _decode_jwt_noop)

    result = runner.invoke(
        app,
        [
            "--context",
            "dev",
            "auth",
            "login",
            "--base-url",
            "https://dev.example.com",
            "--username",
            "user",
            "--password",
            "secret",
        ],
    )

    assert_exit_code(result, 0)

    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    dev_context = next(context for context in data["contexts"] if context["name"] == "dev")
    dev_cluster = next(cluster for cluster in data["clusters"] if cluster["name"] == dev_context["cluster"])
    dev_user = next(user for user in data["users"] if user["name"] == dev_context["user"])

    assert dev_cluster["base_url"].rstrip("/") == "https://dev.example.com"
    assert dev_user["token"] == "dev-access-token"
    assert dev_user["refresh_token"] == "dev-refresh-token"


def test_auth_login_unsigned_token_writes_to_selected_context(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_no_oidc)

    result = runner.invoke(
        app,
        [
            "--context",
            "foo",
            "auth",
            "login",
            "--unsigned-token",
            "--email",
            "admin@example.com",
            "--expires-in",
            "1000",
        ],
    )

    assert_exit_code(result, 0)
    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    foo_user = next(user for user in data["users"] if user["name"] == "foo")
    assert foo_user["type"] == "oauth"
    assert data["current_context"] == "foo"
    claims = decode_jwt_claims(foo_user["token"])
    assert claims["sub"] == "admin@example.com"
    assert claims["email"] == "admin@example.com"
    assert claims["exp"] - claims["iat"] == 1000


def test_auth_login_unsigned_token_requires_email() -> None:
    result = runner.invoke(app, ["auth", "login", "--unsigned-token"])

    assert_exit_code(result, 1)
    assert "--email is required" in result.output


def test_auth_login_unsigned_options_require_unsigned_token() -> None:
    result = runner.invoke(app, ["auth", "login", "--email", "admin@example.com"])

    assert_exit_code(result, 1)
    assert "Unsigned token option(s) --email" in result.output
    assert "--unsigned-token" in result.output


def test_auth_login_unsigned_token_fails_when_oidc_enabled(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def discover_full_oidc(url: str, timeout: float = 10.0) -> SimpleNamespace:
        return SimpleNamespace(
            auth_enabled=True,
            issuer="https://idp.example.com",
            client_id="nmp-client",
            token_endpoint="https://idp.example.com/token",
            device_authorization_endpoint="https://idp.example.com/device",
        )

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", discover_full_oidc)

    result = runner.invoke(
        app,
        [
            "--context",
            "foo",
            "auth",
            "login",
            "--unsigned-token",
            "--email",
            "admin@example.com",
        ],
    )

    assert_exit_code(result, 1)
    assert "Cluster has OIDC authentication configured" in result.output


def test_auth_login_unsigned_token_allows_partial_oidc_config(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def discover_partial_oidc(url: str, timeout: float = 10.0) -> SimpleNamespace:
        return SimpleNamespace(
            auth_enabled=True,
            issuer="https://idp.example.com",
            client_id=None,
            token_endpoint=None,
            device_authorization_endpoint=None,
        )

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", discover_partial_oidc)

    result = runner.invoke(
        app,
        [
            "--context",
            "foo",
            "auth",
            "login",
            "--unsigned-token",
            "--email",
            "admin@example.com",
        ],
    )

    assert_exit_code(result, 0)


def test_auth_login_unsigned_token_uses_principal_id_when_provided(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_no_oidc)

    result = runner.invoke(
        app,
        [
            "--context",
            "foo",
            "auth",
            "login",
            "--unsigned-token",
            "--principal-id",
            "principal-123",
            "--email",
            "admin@example.com",
        ],
    )

    assert_exit_code(result, 0)
    with open(oauth_config_file) as f:
        data = yaml.safe_load(f)

    foo_user = next(user for user in data["users"] if user["name"] == "foo")
    claims = decode_jwt_claims(foo_user["token"])
    assert claims["sub"] == "principal-123"
    assert claims["email"] == "admin@example.com"


# ---------------------------------------------------------------------------
# is_auth_disabled helper
# ---------------------------------------------------------------------------


@dataclass
class IsAuthDisabledCase:
    id: str
    auth_enabled: bool | None  # None means the cluster is unreachable (raises)
    expected: bool | None


@pytest.mark.parametrize(
    "case",
    [
        IsAuthDisabledCase(id="disabled", auth_enabled=False, expected=True),
        IsAuthDisabledCase(id="enabled", auth_enabled=True, expected=False),
        IsAuthDisabledCase(id="unreachable", auth_enabled=None, expected=None),
    ],
    ids=lambda c: c.id,
)
def test_is_auth_disabled(monkeypatch: pytest.MonkeyPatch, case: IsAuthDisabledCase) -> None:
    import httpx

    def mock_discover(url: str, timeout: float = 10.0) -> SimpleNamespace:
        if case.auth_enabled is None:
            raise httpx.ConnectError("Connection refused")
        return SimpleNamespace(auth_enabled=case.auth_enabled)

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", mock_discover)
    from nemo_platform_ext.cli.commands.auth import is_auth_disabled

    assert is_auth_disabled("http://localhost:8080") is case.expected


# ---------------------------------------------------------------------------
# auth status when auth disabled
# ---------------------------------------------------------------------------


def test_auth_status_when_auth_disabled_shows_message(oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_disabled)
    result = runner.invoke(app, ["--context", "foo", "auth", "status"])

    assert_exit_code(result, 0)
    assert "Authentication is disabled" in result.output


def test_auth_status_when_auth_disabled_does_not_show_token_details(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_disabled)
    result = runner.invoke(app, ["--context", "foo", "auth", "status"])

    assert_exit_code(result, 0)
    assert "foo-token" not in result.output
    assert "Refresh Token" not in result.output


# ---------------------------------------------------------------------------
# auth logout when auth disabled
# ---------------------------------------------------------------------------


def test_auth_logout_when_auth_disabled_shows_message_and_skips_credential_clear(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", _discover_auth_disabled)
    with patch("nemo_platform_ext.config.config.Config.write") as mock_write:
        result = runner.invoke(app, ["--context", "foo", "auth", "logout"])

    assert_exit_code(result, 0)
    assert "disabled" in result.output
    mock_write.assert_not_called()


def test_auth_logout_when_cluster_unreachable_still_clears_credentials(
    oauth_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def raise_connect_error(url: str, timeout: float = 10.0) -> SimpleNamespace:
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("nemo_platform_ext.cli.commands.auth.discover_nmp_config", raise_connect_error)
    with patch("nemo_platform_ext.config.config.Config.write") as mock_write:
        result = runner.invoke(app, ["--context", "foo", "auth", "logout"])

    assert_exit_code(result, 0)
    mock_write.assert_called_once()
    assert mock_write.call_args.kwargs["context_name"] == "foo"
