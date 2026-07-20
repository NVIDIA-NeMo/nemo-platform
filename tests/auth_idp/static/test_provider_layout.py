# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import yaml

from tests.auth_idp.providers import load_provider_configs_by_mode, load_provider_names_by_mode

pytestmark = [pytest.mark.auth_idp]


def test_provider_name_discovery_does_not_require_grant_secret(monkeypatch):
    monkeypatch.delenv("AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD", raising=False)

    assert "authentik" in load_provider_names_by_mode("compose-ci")


def test_compose_backed_providers_ship_required_assets(monkeypatch):
    monkeypatch.setenv("AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD", "shared-secret")
    for provider in load_provider_configs_by_mode("compose-ci"):
        root = Path(f"contrib/auth/{provider.name}")
        assert provider.compose_file is not None
        assert provider.compose_file.exists()
        assert (root / "gateway").exists()
        assert (root / "README.md").exists()
        assert (root / "manifest.yaml").exists()


def test_reference_only_providers_do_not_require_compose(monkeypatch):
    monkeypatch.setenv("AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD", "shared-secret")
    for provider in load_provider_names_by_mode("reference-only"):
        root = Path(f"contrib/auth/{provider}")
        assert (root / "README.md").exists()
        assert not (root / "docker-compose.yml").exists()


def test_authentik_compose_disables_model_provider_seed_without_ngc_key():
    compose = yaml.safe_load(Path("contrib/auth/authentik/compose/docker-compose.yml").read_text())
    nemo_service = compose["services"]["nemo"]
    nemo_env = nemo_service["environment"]

    assert nemo_env["NMP_SEED_ON_STARTUP"] == "true"
    assert nemo_env["NMP_PLATFORM_SEED_MODEL_PROVIDER_ENABLED"] == "false"
    assert "ports" not in nemo_service


def test_authentik_compose_defaults_support_direct_docker_compose_start():
    compose_path = Path("contrib/auth/authentik/compose/docker-compose.yml")
    compose_text = compose_path.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    password_default = "${AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD:-svc-nemo-token-secret-dev}"
    blueprint_mount = "${AUTHENTIK_BLUEPRINT_DIR:-../helm/files/blueprints}:/blueprints/custom:ro"

    assert compose["name"] == "${COMPOSE_PROJECT_NAME:-nemo-platform-authentik}"
    assert compose["x-authentik-env"]["AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD"] == password_default
    assert compose["services"]["nemo"]["environment"]["AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD"] == password_default
    assert (
        "../.generated/workload-token-private-key.pem:"
        "/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem:ro"
    ) in compose["services"]["nemo"]["volumes"]
    assert "../gateway/envoy.yaml:/etc/envoy/envoy.yaml:ro" in compose["services"]["gateway"]["volumes"]
    assert (
        "${AUTHENTIK_GATEWAY_TLS_DIR:-../.generated/gateway-tls}:/source/tls:ro"
        in compose["services"]["gateway-tls-init"]["volumes"]
    )
    assert blueprint_mount in compose["services"]["authentik-server"]["volumes"]
    assert blueprint_mount in compose["services"]["authentik-worker"]["volumes"]
    assert "./.generated/blueprints" not in compose_text


def test_authentik_compose_uses_liveness_for_container_health_and_routes_status_through_gateway():
    compose = yaml.safe_load(Path("contrib/auth/authentik/compose/docker-compose.yml").read_text())
    envoy = yaml.safe_load(Path("contrib/auth/authentik/gateway/envoy.yaml").read_text())

    nemo_healthcheck = compose["services"]["nemo"]["healthcheck"]["test"]
    assert "http://127.0.0.1:8080/health/live" in nemo_healthcheck[-1]
    assert "/health/ready" not in nemo_healthcheck[-1]

    http_manager = envoy["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"]
    routes = http_manager["route_config"]["virtual_hosts"][0]["routes"]
    route_matches = [route["match"] for route in routes if route.get("route", {}).get("cluster") == "nemo"]
    forwarded_proto_header = [
        {
            "header": {"key": "x-forwarded-proto", "value": "https"},
            "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
        }
    ]
    gateway_ready_route = next(route for route in routes if route["match"] == {"path": "/health/gateway/ready"})
    health_route = next(route for route in routes if route["match"] == {"prefix": "/health/"})
    assert routes.index(gateway_ready_route) < routes.index(health_route)
    assert gateway_ready_route["direct_response"] == {
        "status": 503,
        "body": {"inline_string": '{"status":"not_ready"}'},
    }
    assert {"prefix": "/health/"} in route_matches
    assert {"path": "/status"} in route_matches
    for match in (
        {"prefix": "/.well-known/nemo-platform/"},
        {"prefix": "/apis/"},
        {"prefix": "/health/"},
        {"path": "/status"},
        {"prefix": "/studio/"},
    ):
        route = next(
            route for route in routes if route.get("route", {}).get("cluster") == "nemo" and route["match"] == match
        )
        assert route["request_headers_to_add"] == forwarded_proto_header

    lua_filter = next(
        filter_config
        for filter_config in http_manager["http_filters"]
        if filter_config["name"] == "envoy.filters.http.lua"
    )
    lua_code = lua_filter["typed_config"]["inline_code"]
    assert 'headers:get(":path") ~= "/health/gateway/ready"' in lua_code
    assert 'gateway_ready_http_call(request_handle, "nemo", "nemo", "/health/ready")' in lua_code
    assert (
        'gateway_ready_http_call(request_handle, "authentik", "authentik-server", '
        '"/application/o/nemo/.well-known/openid-configuration")'
    ) in lua_code

    jwt_filter = next(
        filter_config
        for filter_config in http_manager["http_filters"]
        if filter_config["name"] == "envoy.filters.http.jwt_authn"
    )
    jwt_providers = jwt_filter["typed_config"]["providers"]
    assert jwt_providers["authentik_workload"]["audiences"] == [
        "nemo-platform",
        "nemo-platform-cli",
        "nemo-platform-workload",
    ]
    assert jwt_providers["workload_exchange"]["audiences"] == ["nemo-platform"]
    jwt_rules = jwt_filter["typed_config"]["rules"]
    jwt_rule_matches = [rule["match"] for rule in jwt_rules]
    assert {"prefix": "/health/"} in jwt_rule_matches
    assert {"path": "/status"} in jwt_rule_matches


def test_authentik_compose_mounts_workload_token_signing_key():
    compose = yaml.safe_load(Path("contrib/auth/authentik/compose/docker-compose.yml").read_text())
    config = yaml.safe_load(Path("contrib/auth/authentik/config/platform-compose-authentik.yaml").read_text())

    key_mount = (
        "../.generated/workload-token-private-key.pem:"
        "/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem:ro"
    )

    assert key_mount in compose["services"]["nemo"]["volumes"]
    assert (
        config["auth"]["oidc"]["workload_token_private_key_file"]
        == "/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem"
    )


def test_authentik_compose_uses_https_gateway_for_workloads():
    compose = yaml.safe_load(Path("contrib/auth/authentik/compose/docker-compose.yml").read_text())
    config = yaml.safe_load(Path("contrib/auth/authentik/config/platform-compose-authentik.yaml").read_text())
    nemo = compose["services"]["nemo"]
    gateway = compose["services"]["gateway"]
    gateway_tls_init = compose["services"]["gateway-tls-init"]

    assert config["platform"]["base_url"] == "https://nemo-gateway:8080"
    assert config["auth"]["policy_decision_point_base_url"] == "http://127.0.0.1:8080"
    assert nemo["environment"]["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "http://127.0.0.1:8080"
    assert "loopback_address" not in config["platform"]
    assert "service_discovery" not in config["platform"]
    assert config["auth"]["oidc"]["token_endpoint"] == "https://127.0.0.1:18080/application/o/token/"
    assert config["auth"]["oidc"]["workload_token_issuer"] == "https://nemo-gateway:8080/apis/auth"
    assert config["auth"]["oidc"]["workload_token_endpoint"] == "https://nemo-gateway:8080/apis/auth/token"
    assert (
        "https://nemo-gateway:8080/application/o/nemo-workload/" in config["auth"]["oidc"]["workload_subject_issuers"]
    )
    workload_executor = next(
        executor
        for executor in config["jobs"]["executors"]
        if executor["provider"] == "cpu" and executor["profile"] == "workload"
    )
    assert workload_executor["config"]["workload_identity"]["token_endpoint"] == (
        "https://nemo-gateway:8080/application/o/token/"
    )
    assert set(nemo["networks"]) == {"nemo-internal"}
    assert "nemo-direct" not in yaml.safe_dump(nemo)
    assert nemo["depends_on"]["gateway-tls-init"]["condition"] == "service_completed_successfully"
    assert gateway["networks"]["nemo-internal"]["aliases"] == ["nemo-gateway"]
    assert gateway["networks"]["workload"]["aliases"] == ["nemo-gateway"]
    assert gateway["depends_on"]["gateway-tls-init"]["condition"] == "service_completed_successfully"
    assert "gateway-tls:/etc/envoy/tls:ro" in gateway["volumes"]
    assert gateway_tls_init["image"] == (
        "docker.io/library/busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
    )
    assert gateway_tls_init["user"] == "0:0"
    assert gateway_tls_init["entrypoint"][:2] == ["sh", "-euc"]
    assert "chown 101:101 /target/tls/tls.crt /target/tls/tls.key" in gateway_tls_init["entrypoint"][2]
    assert "chmod 600 /target/tls/tls.key" in gateway_tls_init["entrypoint"][2]
    assert compose["volumes"]["gateway-tls"]["name"] == "${AUTHENTIK_GATEWAY_TLS_VOLUME:-authentik_gateway_tls}"
    assert "gateway-tls:/etc/nmp/gateway-tls:ro" in nemo["volumes"]
    assert nemo["environment"]["SSL_CERT_FILE"] == "/etc/nmp/gateway-tls/tls.crt"
    assert nemo["environment"]["REQUESTS_CA_BUNDLE"] == "/etc/nmp/gateway-tls/tls.crt"


def test_authentik_compose_mounts_gateway_ca_into_docker_workloads():
    config = yaml.safe_load(Path("contrib/auth/authentik/config/platform-compose-authentik.yaml").read_text())
    gateway_tls_volume_name = "authentik_gateway_tls"

    workload_executor = next(
        executor
        for executor in config["jobs"]["executors"]
        if executor["provider"] == "cpu" and executor["profile"] == "workload"
    )
    docker_config = workload_executor["config"]

    assert docker_config["env"] == {
        "SSL_CERT_FILE": "/etc/nmp/gateway-tls/tls.crt",
        "REQUESTS_CA_BUNDLE": "/etc/nmp/gateway-tls/tls.crt",
    }
    assert docker_config["storage"]["additional_volume_mounts"] == [
        {
            "volume_name": gateway_tls_volume_name,
            "mount_path": "/etc/nmp/gateway-tls",
        }
    ]
