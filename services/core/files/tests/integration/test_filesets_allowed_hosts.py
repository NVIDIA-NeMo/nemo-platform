# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: fileset creation rejected when NGC/HuggingFace host is not in allowed_external_hosts."""

import uuid
from collections.abc import Iterator

import pytest
from nemo_platform import APIStatusError, NeMoPlatform
from nmp.common.auth import AuthClient, get_auth_client
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig, Configuration
from nmp.core.files.config import FilesConfig
from nmp.core.files.service import FilesService
from nmp.core.secrets.service import SecretsService
from nmp.testing import create_test_client

# Mock auth so fileset create endpoint works (same pattern as integration/conftest.py)
_mock_auth_principal = Principal(id="test@example.com")
_mock_auth_config = AuthConfig(enabled=False)
_mock_auth_client = AuthClient(principal=_mock_auth_principal, config=_mock_auth_config)


def _mock_get_auth_client():
    return _mock_auth_client


FILESET_AUTH_DEPENDENCY_OVERRIDES = {get_auth_client: _mock_get_auth_client}

DEFAULT_WORKSPACE = "default"


@pytest.fixture
def files_config_restrictive_allowed_hosts() -> Iterator[None]:
    """Override Files config so only one host is allowed (not NGC or HuggingFace defaults)."""
    Configuration.set_override(
        FilesConfig(allowed_external_hosts="https://allowed-only.example.com")  # type: ignore[abstract]
    )
    try:
        yield
    finally:
        Configuration.clear_override(FilesConfig)


@pytest.fixture
def sdk_with_restrictive_hosts(
    files_config_restrictive_allowed_hosts: None,
) -> Iterator[NeMoPlatform]:
    """SDK client with Files config override so NGC/HF default hosts are disallowed."""
    with create_test_client(
        FilesService,
        SecretsService,
        dependency_overrides=FILESET_AUTH_DEPENDENCY_OVERRIDES,
    ) as sdk:
        yield sdk


class TestAllowedExternalHostsRejection:
    """Reject fileset creation when NGC or HuggingFace host/endpoint is not in allowlist."""

    def test_create_ngc_fileset_with_disallowed_host_rejected(
        self,
        sdk_with_restrictive_hosts: NeMoPlatform,
    ) -> None:
        """Creating an NGC fileset with host outside allowed_external_hosts returns 400."""
        sdk = sdk_with_restrictive_hosts
        secret_name = f"ngc-dummy-{uuid.uuid4().hex[:8]}"
        sdk.secrets.create(workspace=DEFAULT_WORKSPACE, name=secret_name, value="nvapi-dummy")
        try:
            name = f"ngc-disallowed-{uuid.uuid4().hex[:8]}"
            with pytest.raises(APIStatusError) as exc_info:
                sdk.files.filesets.create(
                    workspace=DEFAULT_WORKSPACE,
                    name=name,
                    storage={
                        "type": "ngc",
                        "host": "https://disallowed.example.com",
                        "org": "nvidia",
                        "team": "team",
                        "target": "some-resource",
                        "api_key_secret": f"{DEFAULT_WORKSPACE}/{secret_name}",
                    },
                )
            assert exc_info.value.status_code == 400
            detail = str(exc_info.value).lower()
            assert "not allowed" in detail or "allowed" in detail, (
                f"Expected 400 with message about host not allowed, got: {exc_info.value}"
            )
        finally:
            try:
                sdk.secrets.delete(workspace=DEFAULT_WORKSPACE, name=secret_name)
            except Exception:
                pass

    def test_create_huggingface_fileset_with_disallowed_endpoint_rejected(
        self,
        sdk_with_restrictive_hosts: NeMoPlatform,
    ) -> None:
        """Creating a HuggingFace fileset with endpoint outside allowed_external_hosts returns 400."""
        sdk = sdk_with_restrictive_hosts
        name = f"hf-disallowed-{uuid.uuid4().hex[:8]}"
        with pytest.raises(APIStatusError) as exc_info:
            sdk.files.filesets.create(
                workspace=DEFAULT_WORKSPACE,
                name=name,
                storage={
                    "type": "huggingface",
                    "repo_id": "some-org/some-repo",
                    "endpoint": "https://disallowed.example.com",
                },
            )
        assert exc_info.value.status_code == 400
        detail = str(exc_info.value).lower()
        assert "not allowed" in detail or "allowed" in detail, (
            f"Expected 400 with message about endpoint not allowed, got: {exc_info.value}"
        )
