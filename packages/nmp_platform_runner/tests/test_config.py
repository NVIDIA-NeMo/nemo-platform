# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nmp.platform_runner import registry
from nmp.platform_runner.config import (
    ResolvedRunConfiguration,
    apply_run_environment,
    default_config_path,
    resolve_run_configuration,
)


@pytest.fixture(autouse=True)
def clear_registry_caches() -> None:
    registry.get_available_services.cache_clear()
    registry.get_available_controllers.cache_clear()


def _make_config(
    *,
    services: set[str] | None = None,
    controllers: set[str] | None = None,
    sidecars: set[str] | None = None,
    host: str = "0.0.0.0",
    port: int = 8080,
    config_path: str = "/nonexistent/nmp-test-config.yaml",
) -> ResolvedRunConfiguration:
    return ResolvedRunConfiguration(
        services=services if services is not None else {"auth", "entities"},
        controllers=controllers if controllers is not None else {"jobs"},
        sidecars=sidecars if sidecars is not None else set(),
        host=host,
        port=port,
        config_path=config_path,
    )


def resolve(**kwargs):
    params = {}
    params.update(kwargs)
    return resolve_run_configuration(**params)


def test_default_config_path_points_to_bundled_local_config():
    path = default_config_path()

    assert path.endswith(("nmp/platform_runner/config/local.yaml", "nemo_platform/services/runner/config/local.yaml"))


def test_no_arguments_defaults_to_all_services_and_default_controllers():
    resolved = resolve()

    assert resolved.services.issuperset(
        {
            "auth",
            "entities",
            "files",
            "inference-gateway",
            "intake",
            "jobs",
            "models",
            "secrets",
            "safe-synthesizer",
        }
    )
    # Default controllers include all available controllers (core + any installed plugins).
    assert resolved.controllers.issuperset({"jobs", "models", "entities"})


def test_service_group_core_resolves_core_services_only():
    resolved = resolve(service_group="core")

    assert resolved.services == {
        "auth",
        "entities",
        "files",
        "inference-gateway",
        "jobs",
        "models",
        "secrets",
    }
    assert resolved.controllers == set()


def test_controller_group_all_resolves_default_controllers():
    resolved = resolve(controller_group="all")

    assert resolved.services == set()
    assert resolved.controllers.issuperset({"jobs", "models", "entities"})


def test_services_and_service_group_are_mutually_exclusive():
    with pytest.raises(ValueError, match="--services cannot be combined with --service-group"):
        resolve(services=["auth"], service_group="all")


def test_controllers_and_controller_group_are_mutually_exclusive():
    with pytest.raises(ValueError, match="--controllers cannot be combined with --controller-group"):
        resolve(controllers=["jobs"], controller_group="all")


def test_invalid_service_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown services: nope"):
        resolve(services=["nope"])


def test_extra_services_are_available_for_resolution():
    with pytest.raises(ValueError, match="Unknown services: custom-service"):
        resolve(services=["custom-service"])


# ---------------------------------------------------------------------------
# Topology regression tests for apply_run_environment
#
# The revert of PR #15 was caused by apply_run_environment unconditionally
# setting NMP_BASE_URL to localhost, which broke k8s controllers that need
# NMP_BASE_URL to point to the API service pod (set by Helm).
#
# These tests inject a plain dict instead of touching os.environ, so they
# cannot leak state to other tests in the suite.
# ---------------------------------------------------------------------------


class TestApplyRunEnvStandalone:
    """Standalone mode: env vars are NOT pre-set. apply_run_environment should populate them."""

    def test_sets_base_url_when_not_present(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"

    def test_sets_embedded_pdp_base_url_from_base_url(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=9090), env=env)
        assert env["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "http://127.0.0.1:9090"

    def test_sets_service_host_when_not_present(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_SERVICE_HOST"] == "127.0.0.1"

    def test_sets_service_port_when_not_present(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=9090), env=env)
        assert env["NMP_SERVICE_PORT"] == "9090"

    def test_normalizes_ipv4_wildcard_to_loopback(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_SERVICE_HOST"] == "127.0.0.1"

    def test_normalizes_ipv6_wildcard_to_loopback(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="::", port=8080), env=env)
        assert env["NMP_SERVICE_HOST"] == "::1"

    def test_ipv6_loopback_brackets_in_url(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="::", port=8080), env=env)
        assert env["NMP_BASE_URL"] == "http://[::1]:8080"

    def test_sets_services_and_controllers(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(services={"auth", "files"}, controllers={"jobs"}), env=env)
        assert env["NMP_SERVICES"] == "auth,files"
        assert env["NMP_CONTROLLERS"] == "jobs"

    def test_clears_empty_sidecars(self):
        env: dict[str, str] = {"NMP_SIDECARS": "old-value"}
        apply_run_environment(_make_config(sidecars=set()), env=env)
        assert "NMP_SIDECARS" not in env


class TestApplyRunEnvDeployed:
    """Deployed mode: env vars are pre-set by Helm/k8s. apply_run_environment must NOT overwrite them.

    This is the regression that caused the revert of PR #15. Controllers in k8s
    run in separate pods where NMP_BASE_URL must point to the API service, not localhost.
    """

    def test_preserves_existing_base_url(self):
        env: dict[str, str] = {"NMP_BASE_URL": "http://nemo-platform-api:8080"}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_BASE_URL"] == "http://nemo-platform-api:8080"

    def test_preserves_existing_embedded_pdp_base_url(self):
        env: dict[str, str] = {
            "NMP_BASE_URL": "http://nemo-platform-api:8080",
            "NMP_AUTH_POLICY_DECISION_POINT_BASE_URL": "http://nemo-auth:8080",
        }
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "http://nemo-auth:8080"

    def test_preserves_existing_service_host(self):
        env: dict[str, str] = {"NMP_SERVICE_HOST": "nemo-platform-api"}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_SERVICE_HOST"] == "nemo-platform-api"

    def test_preserves_existing_service_port(self):
        env: dict[str, str] = {"NMP_SERVICE_PORT": "443"}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_SERVICE_PORT"] == "443"

    def test_derives_base_url_from_effective_host_port(self):
        """If Helm sets host/port but not NMP_BASE_URL, derive it from the effective values."""
        env: dict[str, str] = {
            "NMP_SERVICE_HOST": "nemo-platform-api",
            "NMP_SERVICE_PORT": "9090",
        }
        apply_run_environment(_make_config(host="0.0.0.0", port=8080), env=env)
        assert env["NMP_BASE_URL"] == "http://nemo-platform-api:9090"


class TestApplyRunEnvConfigBaseUrl:
    """Standalone mode with an explicit platform.base_url in the config file.

    The config value's *host* must seed NMP_BASE_URL (instead of the
    bind-derived loopback default) so operators can set a container-reachable
    base URL via config alone — but paired with the actual bind port, not the
    port hardcoded in the config. An externally-provided NMP_BASE_URL still
    wins.
    """

    def _write_config(self, tmp_path: Path, body: str) -> str:
        path = tmp_path / "config.yaml"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_seeds_base_url_host_from_config_file(self, tmp_path: Path):
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://172.17.0.1:8080\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://172.17.0.1:8080"
        # Embedded PDP base URL follows NMP_BASE_URL.
        assert env["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "http://172.17.0.1:8080"

    def test_uses_actual_bind_port_not_config_port(self, tmp_path: Path):
        # The config hardcodes :8080 but the platform is launched on 59007
        # (as the e2e harness does). NMP_BASE_URL must carry the real bind port
        # so internal in-process clients can reach the server.
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://172.17.0.1:8080\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=59007, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://172.17.0.1:59007"
        assert env["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "http://172.17.0.1:59007"

    def test_config_base_url_without_port_gets_bind_port(self, tmp_path: Path):
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://172.17.0.1\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=9090, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://172.17.0.1:9090"

    def test_external_env_still_wins_over_config_file(self, tmp_path: Path):
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://172.17.0.1:8080\n")
        env: dict[str, str] = {"NMP_BASE_URL": "http://nemo-platform-api:8080"}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://nemo-platform-api:8080"

    def test_falls_back_to_bind_derived_when_config_omits_base_url(self, tmp_path: Path):
        config_path = self._write_config(tmp_path, "platform:\n  runtime: docker\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"

    def test_falls_back_to_bind_derived_when_config_file_missing(self):
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path="/nonexistent/nmp.yaml"), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"

    def test_preserves_https_scheme_from_config(self, tmp_path: Path):
        # A configured https:// base URL must not be downgraded to http://.
        config_path = self._write_config(tmp_path, "platform:\n  base_url: https://172.17.0.1:8080\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=9090, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "https://172.17.0.1:9090"
        assert env["NMP_AUTH_POLICY_DECISION_POINT_BASE_URL"] == "https://172.17.0.1:9090"

    def test_malformed_ipv6_config_falls_back_to_bind_derived(self, tmp_path: Path):
        # An unterminated bracketed IPv6 makes urlparse raise ValueError; that
        # must fail soft to the bind-derived default rather than abort startup.
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://[::1\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"

    def test_wildcard_host_in_config_normalized_to_loopback(self, tmp_path: Path):
        # The bundled local.yaml sets platform.base_url: http://0.0.0.0:8080.
        # 0.0.0.0 is a bind-only wildcard, so the seeded internal base URL must
        # be normalized to loopback or in-process clients (PDP, readiness) break.
        config_path = self._write_config(tmp_path, "platform:\n  base_url: http://0.0.0.0:8080\n")
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=config_path), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"

    def test_bundled_default_config_seeds_loopback(self):
        # Regression guard for the real default path: `nemo services run` with no
        # --config uses default_config_path() (bundled local.yaml, which sets
        # http://0.0.0.0:8080). The seeded NMP_BASE_URL must be connectable.
        env: dict[str, str] = {}
        apply_run_environment(_make_config(host="0.0.0.0", port=8080, config_path=default_config_path()), env=env)
        assert env["NMP_BASE_URL"] == "http://127.0.0.1:8080"
