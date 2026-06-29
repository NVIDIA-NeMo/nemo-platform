# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import yaml

from tests.auth_idp.providers import load_provider_names_by_mode

REQUIRED_STRIPPED_HEADERS = {
    "x-nmp-principal-id",
    "x-nmp-principal-email",
    "x-nmp-principal-groups",
    "x-nmp-principal-on-behalf-of",
    "x-nmp-principal-on-behalf-of-email",
    "x-nmp-principal-on-behalf-of-groups",
}


def test_compose_backed_idp_providers_are_discovered_from_manifests():
    providers = load_provider_names_by_mode("compose-ci")
    assert providers
    for provider in providers:
        assert Path(f"contrib/auth/{provider}/gateway/envoy.yaml").exists()


def test_all_compose_backed_gateways_strip_trusted_identity_headers():
    for provider in load_provider_names_by_mode("compose-ci"):
        config = yaml.safe_load(Path(f"contrib/auth/{provider}/gateway/envoy.yaml").read_text())
        virtual_host = config["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"][
            "route_config"
        ]["virtual_hosts"][0]
        stripped_headers = set(virtual_host["request_headers_to_remove"])
        assert REQUIRED_STRIPPED_HEADERS.issubset(stripped_headers)


def test_all_compose_backed_gateways_define_minimal_envoy_runtime():
    for provider in load_provider_names_by_mode("compose-ci"):
        config = yaml.safe_load(Path(f"contrib/auth/{provider}/gateway/envoy.yaml").read_text())
        listener = config["static_resources"]["listeners"][0]
        cluster = config["static_resources"]["clusters"][0]
        assert listener["name"]
        assert cluster["name"] == "nemo"
