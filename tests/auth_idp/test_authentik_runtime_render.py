# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import yaml

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_E2E_CONFIG
from tests.auth_idp.runtime import get_authentik_docker_test_runtime

pytestmark = [pytest.mark.auth_idp]


def test_get_authentik_docker_test_runtime_uses_checked_in_compose_stack():
    runtime = get_authentik_docker_test_runtime()

    assert runtime.compose_file == Path("contrib/auth/authentik/docker-compose.yml")
    assert runtime.nemo_config == Path("contrib/auth/authentik/config/platform-compose-authentik.yaml")
    assert runtime.gateway_base_url == "http://127.0.0.1:18080"
    assert runtime.token_endpoint == "http://127.0.0.1:18080/application/o/token/"


def test_authentik_live_marker_uses_compose_harness_metadata():
    expected_lifecycle = AUTHENTIK_DOCKER_E2E_CONFIG.kwargs["harness"]["env"]["AUTHENTIK_E2E_LIFECYCLE"]
    expected_workload_network = AUTHENTIK_DOCKER_E2E_CONFIG.kwargs["harness"]["env"]["AUTHENTIK_WORKLOAD_NETWORK_NAME"]
    assert AUTHENTIK_DOCKER_E2E_CONFIG.args == (
        "contrib/auth/authentik/config/platform-compose-authentik.yaml",
        {
            "auth": {
                "oidc": {
                    "additional_issuers": [
                        "http://authentik-server:9000/application/o/nemo/",
                        "http://127.0.0.1:38080/application/o/nemo-cli/",
                        "http://127.0.0.1:38080/application/o/nemo/",
                    ],
                    "token_endpoint": "http://127.0.0.1:38080/application/o/token/",
                    "device_authorization_endpoint": "http://127.0.0.1:38080/application/o/device/",
                }
            }
        },
    )
    assert AUTHENTIK_DOCKER_E2E_CONFIG.kwargs == {
        "harness": {
            "backend": "docker_compose",
            "compose_file": "contrib/auth/authentik/docker-compose.yml",
            "compose_project_name": "authentik-e2e",
            "service_url": "http://127.0.0.1:38080",
            "wait_url": "http://127.0.0.1:38080/application/o/nemo/.well-known/openid-configuration",
            "env": {
                "AUTHENTIK_GATEWAY_PORT": "38080",
                "AUTHENTIK_E2E_LIFECYCLE": expected_lifecycle,
                "AUTHENTIK_WORKLOAD_NETWORK_NAME": expected_workload_network,
            },
        }
    }
    assert expected_workload_network == "authentik-e2e_workload"


def test_authentik_make_target_defaults_full_suite_to_fresh():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "AUTHENTIK_E2E_LIFECYCLE ?= fresh" in makefile
    assert (
        "AUTHENTIK_E2E_LIFECYCLE=$(AUTHENTIK_E2E_LIFECYCLE) uv run --frozen pytest tests/auth_idp -v --run-e2e"
    ) in makefile


def test_authentik_compose_uses_split_network_topology():
    compose = yaml.safe_load(Path("contrib/auth/authentik/docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["networks"]["nemo-internal"] == {}
    assert compose["networks"]["workload"]["name"] == "${AUTHENTIK_WORKLOAD_NETWORK_NAME:-authentik_workload}"
    assert compose["services"]["nemo"]["networks"] == ["nemo-internal"]
    assert compose["services"]["gateway"]["networks"]["nemo-internal"] == {}
    assert compose["services"]["gateway"]["networks"]["workload"]["aliases"] == ["nemo-gateway"]


def test_authentik_compose_uses_platform_default_image():
    compose = yaml.safe_load(Path("contrib/auth/authentik/docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["nemo"]["image"] == "${IMAGE_REGISTRY:-my-registry}/nmp-api:${BAKE_TAG:-local}"


def test_authentik_compose_sets_workload_job_network_env():
    compose = yaml.safe_load(Path("contrib/auth/authentik/docker-compose.yml").read_text(encoding="utf-8"))

    assert (
        compose["services"]["nemo"]["environment"]["NEMO_JOBS_DEFAULT_DOCKER_NETWORK"]
        == "${AUTHENTIK_WORKLOAD_NETWORK_NAME:-authentik_workload}"
    )


def test_authentik_platform_config_routes_job_sdk_calls_to_gateway_alias():
    config = yaml.safe_load(
        Path("contrib/auth/authentik/config/platform-compose-authentik.yaml").read_text(encoding="utf-8")
    )

    assert config["platform"]["loopback_address"] == "nemo-gateway"


def test_authentik_platform_config_exposes_docker_workload_profile_for_live_job_check():
    config = yaml.safe_load(
        Path("contrib/auth/authentik/config/platform-compose-authentik.yaml").read_text(encoding="utf-8")
    )

    executors = {(executor["provider"], executor["profile"]): executor for executor in config["jobs"]["executors"]}
    workload = executors[("cpu", "workload")]

    assert workload["backend"] == "docker"
    assert workload["config"]["cleanup_completed_jobs_immediately"] is False
    assert workload["config"]["launcher_tool_path"] == "/tools/jobs-launcher"


def test_authentik_gateway_strips_spoofed_headers_before_jwt_claim_forwarding():
    envoy = yaml.safe_load(Path("contrib/auth/authentik/gateway/envoy.yaml").read_text(encoding="utf-8"))
    http_manager = envoy["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"]
    virtual_host = http_manager["route_config"]["virtual_hosts"][0]
    http_filters = http_manager["http_filters"]

    assert "request_headers_to_remove" not in virtual_host
    assert [http_filter["name"] for http_filter in http_filters[:2]] == [
        "envoy.filters.http.lua",
        "envoy.filters.http.jwt_authn",
    ]

    lua_code = http_filters[0]["typed_config"]["inline_code"]
    assert 'headers:remove("x-nmp-principal-id")' in lua_code
    assert 'headers:remove("x-nmp-principal-groups")' in lua_code


def test_authentik_gateway_accepts_confidential_and_cli_token_audiences():
    envoy = yaml.safe_load(Path("contrib/auth/authentik/gateway/envoy.yaml").read_text(encoding="utf-8"))
    http_manager = envoy["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"]
    jwt_authn = next(
        http_filter
        for http_filter in http_manager["http_filters"]
        if http_filter["name"] == "envoy.filters.http.jwt_authn"
    )

    provider = jwt_authn["typed_config"]["providers"]["authentik_workload"]

    assert provider["audiences"] == ["nemo-platform", "nemo-platform-cli"]
