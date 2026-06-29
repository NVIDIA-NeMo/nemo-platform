# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import yaml

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_E2E_CONFIG
from tests.auth_idp.runtime import (
    authentik_runtime_compose_env,
    authentik_runtime_compose_files,
    configure_authentik_gateway_upstream,
    finalize_authentik_runtime_bundle,
    get_authentik_docker_test_runtime,
    render_authentik_runtime_bundle,
)

pytestmark = [pytest.mark.auth_idp]


def test_render_authentik_runtime_bundle_rewrites_runtime_urls(tmp_path: Path):
    runtime = render_authentik_runtime_bundle(
        runtime_root=tmp_path,
        gateway_host_port=28180,
        issuer_host_port=29100,
        compose_project_name="authentik-e2e-test",
    )

    compose = yaml.safe_load(runtime.compose_file.read_text())
    assert compose["services"]["gateway"]["volumes"] == [
        f"{(tmp_path / 'gateway' / 'envoy.yaml').resolve()}:/etc/envoy/envoy.yaml:ro"
    ]
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "blueprints").exists()
    assert runtime.compose_file.name == "docker-compose.override.yml"

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text())
    assert manifest["gateway_base_url"] == "http://127.0.0.1:28180"
    assert manifest["issuer_url"] == "http://127.0.0.1:29100/application/o/nemo/"
    assert manifest["token_acquisition"]["token_endpoint"] == "http://127.0.0.1:29100/application/o/token/"
    assert (
        manifest["healthchecks"][0]["url"]
        == "http://127.0.0.1:29100/application/o/nemo/.well-known/openid-configuration"
    )

    nemo_auth = yaml.safe_load(runtime.nemo_config.read_text())
    assert nemo_auth["auth"]["oidc"]["issuer"] == "http://127.0.0.1:29100/application/o/nemo/"

    envoy_content = (tmp_path / "gateway" / "envoy.yaml").read_text()
    assert "address: nemo" in envoy_content

    assert runtime.compose_project_name == "authentik-e2e-test"
    assert runtime.gateway_base_url == "http://127.0.0.1:28180"
    assert runtime.token_endpoint == "http://127.0.0.1:29100/application/o/token/"


def test_render_authentik_runtime_bundle_can_override_nemo_auth_issuer(tmp_path: Path):
    runtime = render_authentik_runtime_bundle(
        runtime_root=tmp_path,
        gateway_host_port=28180,
        issuer_host_port=29100,
        compose_project_name="authentik-e2e-test",
        nemo_auth_issuer_url="http://authentik-server:9000/application/o/nemo/",
    )

    nemo_auth = yaml.safe_load(runtime.nemo_config.read_text())
    assert nemo_auth["auth"]["oidc"]["issuer"] == "http://authentik-server:9000/application/o/nemo/"


def test_render_authentik_runtime_bundle_can_defer_to_docker_published_ports(tmp_path: Path):
    runtime = render_authentik_runtime_bundle(
        runtime_root=tmp_path,
        gateway_host_port=None,
        issuer_host_port=None,
        compose_project_name="authentik-e2e-test",
    )

    compose = yaml.safe_load(runtime.compose_file.read_text())
    assert "ports" not in compose["services"]["gateway"]
    assert runtime.gateway_base_url == "http://127.0.0.1:0"
    assert runtime.token_endpoint == "http://127.0.0.1:0/application/o/token/"


def test_authentik_runtime_compose_env_defaults_to_docker_assigned_host_ports():
    assert authentik_runtime_compose_env(None, None) == {
        "AUTHENTIK_GATEWAY_PORT": "0",
        "AUTHENTIK_ISSUER_PORT": "0",
    }


def test_authentik_runtime_compose_env_supports_explicit_host_ports():
    assert authentik_runtime_compose_env(28180, 29100) == {
        "AUTHENTIK_GATEWAY_PORT": "28180",
        "AUTHENTIK_ISSUER_PORT": "29100",
    }


def test_finalize_authentik_runtime_bundle_rewrites_runtime_urls_after_startup(tmp_path: Path):
    render_authentik_runtime_bundle(
        runtime_root=tmp_path,
        gateway_host_port=None,
        issuer_host_port=None,
        compose_project_name="authentik-e2e-test",
    )

    runtime = finalize_authentik_runtime_bundle(
        tmp_path,
        gateway_host_port=28180,
        issuer_host_port=29100,
        compose_project_name="authentik-e2e-test",
    )

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text())
    assert manifest["gateway_base_url"] == "http://127.0.0.1:28180"
    assert manifest["issuer_url"] == "http://127.0.0.1:29100/application/o/nemo/"
    assert runtime.gateway_base_url == "http://127.0.0.1:28180"
    assert runtime.token_endpoint == "http://127.0.0.1:29100/application/o/token/"


def test_get_authentik_docker_test_runtime_uses_checked_in_compose_nemo_config():
    runtime = get_authentik_docker_test_runtime()

    assert runtime.compose_file == Path("contrib/auth/authentik/docker-compose.yml")
    assert runtime.nemo_config == Path("contrib/auth/authentik/config/platform-compose-authentik.yaml")
    assert runtime.token_endpoint == "http://127.0.0.1:19000/application/o/token/"


def test_authentik_live_marker_uses_single_checked_in_compose_config():
    assert AUTHENTIK_DOCKER_E2E_CONFIG.args[0] == "contrib/auth/authentik/config/platform-compose-authentik.yaml"
    assert AUTHENTIK_DOCKER_E2E_CONFIG.args[1:] == (
        {
            "e2e_sidecars": {
                "authentik": {
                    "provider": "authentik",
                }
            }
        },
    )


def test_authentik_runtime_compose_files_include_base_and_override(tmp_path: Path):
    assert authentik_runtime_compose_files(tmp_path) == (
        Path("contrib/auth/authentik/docker-compose.yml"),
        tmp_path / "docker-compose.override.yml",
    )


def test_configure_authentik_gateway_upstream_can_target_same_docker_network(tmp_path: Path):
    render_authentik_runtime_bundle(
        runtime_root=tmp_path,
        gateway_host_port=28180,
        issuer_host_port=29100,
        compose_project_name="authentik-e2e-test",
    )

    configure_authentik_gateway_upstream(
        tmp_path,
        upstream_host="nmp-quickstart",
        upstream_port=8080,
        external_network_name="nmp-quickstart-network",
    )

    envoy = yaml.safe_load((tmp_path / "gateway" / "envoy.yaml").read_text())
    socket_address = envoy["static_resources"]["clusters"][0]["load_assignment"]["endpoints"][0]["lb_endpoints"][0][
        "endpoint"
    ]["address"]["socket_address"]
    assert socket_address["address"] == "nmp-quickstart"
    assert socket_address["port_value"] == 8080

    compose = yaml.safe_load((tmp_path / "docker-compose.override.yml").read_text())
    assert compose["networks"]["default"] == {
        "name": "nmp-quickstart-network",
        "external": True,
    }
