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
    principal_contract = manifest["principal_contract"]
    workload_identity = manifest["workload_identity"]
    workload_contract = manifest["workload_contract"]

    assert token_acquisition["token_endpoint"]
    assert token_acquisition["human_grant"]["grant_type"] == "password"
    assert token_acquisition["machine_grant"]["grant_type"] == "password"
    assert token_acquisition["human_grant"]["client_id"]
    assert token_acquisition["machine_grant"]["client_id"]
    assert token_acquisition["human_grant"]["password"] == "nemo-user-token-secret-dev"
    assert "offline_access" in token_acquisition["human_grant"]["scope"].split()
    assert workload_identity["principal_id"]
    assert not workload_identity["principal_id"].startswith(principal_contract["internal_service_prefix_reserved"])
    assert workload_identity["expected_groups"]
    assert workload_contract["audience"] == "nemo-platform"
    assert workload_contract["groups_format"] == "comma_string"
    assert workload_contract["forwarded_headers"]["principal_id"] == "X-NMP-Principal-Id"
    assert workload_contract["forwarded_headers"]["principal_groups"] == "X-NMP-Principal-Groups"


def test_authentik_manifest_declares_extended_startup_timeouts_for_real_oidc():
    manifest = yaml.safe_load(Path("contrib/auth/authentik/manifest.yaml").read_text())
    startup_timeouts = manifest["startup_timeouts"]

    assert startup_timeouts["healthchecks_seconds"] >= 240
    assert startup_timeouts["gateway_seconds"] >= 30
    assert startup_timeouts["token_endpoint_seconds"] >= 60


def test_authentik_provider_config_loads_token_acquisition_fields():
    provider = next(config for config in load_provider_configs() if config.name == "authentik")

    assert provider.nemo_config == Path("contrib/auth/authentik/config/platform-compose-authentik.yaml")
    assert provider.token_endpoint == "http://127.0.0.1:18080/application/o/token/"
    assert provider.human_grant["grant_type"] == "password"
    assert provider.machine_grant["grant_type"] == "password"
    assert provider.workload_audience == "nemo-platform"
    assert provider.workload_principal_claim == "sub"
    assert provider.workload_groups_claim == "groups"
    assert provider.workload_groups_format == "comma_string"
    assert provider.workload_token_env_vars == ["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"]
    assert provider.startup_timeouts == {
        "healthchecks_seconds": 600,
        "gateway_seconds": 30,
        "token_endpoint_seconds": 180,
    }
