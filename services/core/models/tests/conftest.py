# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from nmp.common.config import AuthConfig


@pytest.fixture(scope="session")
def _files_runtime_signing_key_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate one shared API signing key for model runtime-token tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_file: Path = tmp_path_factory.mktemp("files-runtime-token") / "private-key.pem"
    key_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return key_file


@pytest.fixture(autouse=True)
def _files_runtime_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    _files_runtime_signing_key_file: Path,
) -> None:
    """Scope the runtime-token auth configuration to each model test."""
    config = AuthConfig(enabled=True)
    config.oidc.workload_token_private_key_file = str(_files_runtime_signing_key_file)

    from nmp.common.auth import dependencies
    from nmp.core.models.controllers.backends.deployments_plugin import runtime_auth

    monkeypatch.setattr(dependencies, "get_auth_config", lambda: config)
    monkeypatch.setattr(runtime_auth, "get_auth_config", lambda: config)
