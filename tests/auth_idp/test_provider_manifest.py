# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import yaml
from jsonschema.validators import validator_for

from tests.auth_idp.providers import load_provider_configs

pytestmark = [pytest.mark.auth_idp]


def _load_provider_manifest_schema() -> dict:
    return yaml.safe_load(Path("contrib/auth/manifest.schema.yaml").read_text())


def test_all_provider_manifests_share_the_same_contract():
    schema = _load_provider_manifest_schema()
    validator = validator_for(schema)(schema)
    for provider in load_provider_configs():
        manifest = yaml.safe_load(Path(f"contrib/auth/{provider.name}/manifest.yaml").read_text())
        validator.validate(manifest)
        assert manifest["provider"] == provider.name


def test_authentik_manifest_declares_real_token_acquisition_contract():
    manifest = yaml.safe_load(Path("contrib/auth/authentik/manifest.yaml").read_text())
    token_acquisition = manifest["token_acquisition"]

    assert token_acquisition["token_endpoint"]
    assert token_acquisition["human_grant"]["grant_type"] == "password"
    assert token_acquisition["machine_grant"]["grant_type"] == "client_credentials"
    assert token_acquisition["human_grant"]["client_id"]
    assert token_acquisition["machine_grant"]["client_id"]


def test_authentik_manifest_declares_extended_startup_timeouts_for_real_oidc():
    manifest = yaml.safe_load(Path("contrib/auth/authentik/manifest.yaml").read_text())
    startup_timeouts = manifest["startup_timeouts"]

    assert startup_timeouts["healthchecks_seconds"] >= 240
    assert startup_timeouts["gateway_seconds"] >= 30
    assert startup_timeouts["token_endpoint_seconds"] >= 60
