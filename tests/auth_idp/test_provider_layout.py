# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import yaml

from tests.auth_idp.providers import load_provider_names_by_mode

pytestmark = [pytest.mark.auth_idp]


def test_compose_backed_providers_ship_required_assets():
    for provider in load_provider_names_by_mode("compose-ci"):
        root = Path(f"contrib/auth/{provider}")
        assert (root / "docker-compose.yml").exists()
        assert (root / "gateway").exists()
        assert (root / "README.md").exists()
        assert (root / "manifest.yaml").exists()


def test_reference_only_providers_do_not_require_compose():
    for provider in load_provider_names_by_mode("reference-only"):
        root = Path(f"contrib/auth/{provider}")
        assert (root / "README.md").exists()
        assert not (root / "docker-compose.yml").exists()


def test_authentik_compose_disables_model_provider_seed_without_ngc_key():
    compose = yaml.safe_load(Path("contrib/auth/authentik/docker-compose.yml").read_text())
    nemo_service = compose["services"]["nemo"]
    nemo_env = nemo_service["environment"]

    assert nemo_env["NMP_SEED_ON_STARTUP"] == "true"
    assert nemo_env["NMP_PLATFORM_SEED_MODEL_PROVIDER_ENABLED"] == "false"
    assert "${NEMO_DIRECT_PORT:-18081}:8080" in nemo_service["ports"]
