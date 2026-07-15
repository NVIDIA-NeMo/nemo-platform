# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration resolution for the platform runner."""

from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from importlib.resources import files
from urllib.parse import urlparse

from nmp.common.config import (
    NMP_CONFIG_FILE_PATH_ENV_VAR,
    NMP_CONTROLLERS_ENV_VAR,
    NMP_SERVICES_ENV_VAR,
    NMP_SIDECARS_ENV_VAR,
    Configuration,
)
from nmp.common.service import Service
from nmp.platform_runner.registry import (
    AVAILABLE_SIDECARS,
    get_available_controllers,
    get_available_services,
    get_controller_groups,
    get_default_controllers,
    get_service_groups,
)

_IPV4_LOOPBACK = "127.0.0.1"
_IPV6_LOOPBACK = "::1"
_IPV4_WILDCARDS = frozenset({"0.0.0.0"})
_IPV6_WILDCARDS = frozenset({"::", "[::]"})


@dataclass
class ResolvedRunConfiguration:
    services: set[str]
    controllers: set[str]
    sidecars: set[str]
    host: str
    port: int
    config_path: str
    available_services: dict[str, str | Service] = field(default_factory=dict)
    available_controllers: dict[str, str | Callable] = field(default_factory=dict)


def default_config_path() -> str:
    """Return the bundled local config path."""
    return os.environ.get(
        NMP_CONFIG_FILE_PATH_ENV_VAR,
        str(files("nmp.platform_runner").joinpath("config/local.yaml")),
    )


def resolve_run_configuration(
    *,
    services: list[str] | None = None,
    service_group: str | None = None,
    controllers: list[str] | None = None,
    controller_group: str | None = None,
    sidecars: list[str] | None = None,
    config_path: str | None = None,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> ResolvedRunConfiguration:
    """Resolve and validate platform run arguments.

    Group selectors are convenience shortcuts for callers that are not also
    naming specific services or controllers. Mixing the two is ambiguous, so
    these combinations fail fast instead of silently ignoring the group.
    """
    available_services = get_available_services()
    available_controllers = get_available_controllers()
    available_sidecars = AVAILABLE_SIDECARS
    service_groups = get_service_groups(available_services)
    controller_groups = get_controller_groups(available_controllers)
    default_controllers = set(get_default_controllers(controller_groups))

    selected_services = set(services or [])
    selected_controllers = set(controllers or [])
    selected_sidecars = set(sidecars or [])

    # Explicit selections and group selectors are mutually exclusive. The old
    # entrypoint rejected these combinations, and keeping that behavior avoids a
    # confusing silent-ignore UX for callers.
    if service_group and selected_services:
        raise ValueError("--services cannot be combined with --service-group")

    if controller_group and selected_controllers:
        raise ValueError("--controllers cannot be combined with --controller-group")

    if service_group and not selected_services:
        if service_group not in service_groups:
            valid_groups = ", ".join(sorted(service_groups))
            raise ValueError(f"Unknown service group: {service_group}. Available groups: {valid_groups}")
        selected_services.update(service_groups[service_group])

    if controller_group and not selected_controllers:
        if controller_group not in controller_groups:
            valid_groups = ", ".join(sorted(controller_groups))
            raise ValueError(f"Unknown controller group: {controller_group}. Available groups: {valid_groups}")
        selected_controllers.update(controller_groups[controller_group])

    invalid_services = selected_services - set(available_services)
    if invalid_services:
        available = ", ".join(sorted(available_services))
        requested = ", ".join(sorted(invalid_services))
        raise ValueError(f"Unknown services: {requested}. Available services: {available}")

    invalid_controllers = selected_controllers - set(available_controllers)
    if invalid_controllers:
        available = ", ".join(sorted(available_controllers))
        requested = ", ".join(sorted(invalid_controllers))
        raise ValueError(f"Unknown controllers: {requested}. Available controllers: {available}")

    invalid_sidecars = selected_sidecars - set(available_sidecars)
    if invalid_sidecars:
        available = ", ".join(sorted(available_sidecars))
        requested = ", ".join(sorted(invalid_sidecars))
        raise ValueError(f"Unknown sidecars: {requested}. Available sidecars: {available}")

    if not selected_services and not selected_controllers and not selected_sidecars:
        # No explicit selection means "run the platform": start the default
        # service group plus the default controller set.
        selected_services.update(service_groups["all"])
        selected_controllers.update(default_controllers)

    return ResolvedRunConfiguration(
        services=selected_services,
        controllers=selected_controllers,
        sidecars=selected_sidecars,
        host=host,
        port=port,
        config_path=config_path or default_config_path(),
        available_services=available_services,
        available_controllers=available_controllers,
    )


def apply_run_environment(
    config: ResolvedRunConfiguration,
    env: MutableMapping[str, str] | None = None,
) -> None:
    """Apply the resolved run configuration to process environment variables.

    Args:
        config: The resolved configuration to apply.
        env: Environment mapping to write to. Defaults to ``os.environ``.
            Accepting an explicit mapping makes this function trivially
            testable without monkeypatching or snapshot fixtures.

    Uses ``setdefault`` for NMP_BASE_URL / NMP_SERVICE_HOST / NMP_SERVICE_PORT
    so that values pre-set by Helm / k8s (deployed mode) are never overwritten.
    In standalone mode these variables are absent, so setdefault fills them in.

    Precedence for NMP_BASE_URL: an externally-provided value (Helm / k8s) wins,
    then the scheme + host of an explicit ``platform.base_url`` from the config
    file combined with the actual bind port, then a value derived entirely from
    the bind host/port. Seeding from the config file lets operators set a base
    URL reachable from inside deployed agent containers (e.g. the Docker bridge
    address) via config alone; without this the bind-derived loopback default
    would silently shadow the configured value.

    Only the scheme and host of the configured ``platform.base_url`` are
    honored — its port is replaced with the port the server actually binds. A
    config that hardcodes ``:8080`` must not point internal clients (and the
    embedded PDP) at 8080 when the platform is launched on another port (which
    the e2e harness always does, and any ``nemo services run --port`` differing
    from 8080 does); doing so leaves internal HTTP clients unable to reach the
    server and the platform never becomes ready. The configured host is run
    through the same wildcard -> loopback normalization as the bind host, so a
    config like ``http://0.0.0.0:8080`` (the bundled ``local.yaml`` default)
    still yields a connectable internal base URL.
    """
    if env is None:
        env = os.environ
    env[NMP_CONFIG_FILE_PATH_ENV_VAR] = config.config_path
    connect_host = _connect_host_for_internal_clients(config.host)
    effective_host = env.setdefault("NMP_SERVICE_HOST", connect_host)
    effective_port = env.setdefault("NMP_SERVICE_PORT", str(config.port))
    config_base_url_parts = _config_file_base_url_parts(config.config_path)
    if config_base_url_parts is not None:
        scheme, config_host = config_base_url_parts
        host_for_url = _bracket_ipv6(_connect_host_for_internal_clients(config_host))
        default_base_url = f"{scheme}://{host_for_url}:{effective_port}"
    else:
        host_for_url = _bracket_ipv6(effective_host)
        default_base_url = f"http://{host_for_url}:{effective_port}"
    base_url = env.setdefault("NMP_BASE_URL", default_base_url)
    # Embedded PDP is served from the same platform process; keep the auth client
    # origin aligned with NMP_BASE_URL when services run on a non-default port.
    env.setdefault("NMP_AUTH_POLICY_DECISION_POINT_BASE_URL", base_url)
    _set_or_clear_env(env, NMP_SERVICES_ENV_VAR, config.services)
    _set_or_clear_env(env, NMP_CONTROLLERS_ENV_VAR, config.controllers)
    _set_or_clear_env(env, NMP_SIDECARS_ENV_VAR, config.sidecars)
    Configuration.clear_cache()


def _set_or_clear_env(env: MutableMapping[str, str], name: str, values: set[str]) -> None:
    if values:
        env[name] = ",".join(sorted(values))
    else:
        env.pop(name, None)


def _config_file_base_url_parts(config_path: str) -> tuple[str, str] | None:
    """Return the (scheme, host) of an explicit ``platform.base_url`` from config.

    Reads the raw YAML rather than the merged config object so a value present
    in the file can be told apart from the schema default (the merged config
    always carries ``base_url``). Returns the URL scheme (defaulting to
    ``"http"`` when the config omits one) and the host component, or ``None``
    when the file is missing, unreadable, does not set ``platform.base_url``, or
    the value has no parseable host.

    The host is returned unbracketed (as ``urlparse`` yields it) so callers can
    normalize it (e.g. wildcard -> loopback) before composing the final URL.
    Only the scheme and host are returned — callers pair them with the actual
    bind port, so a config that hardcodes a port (e.g. ``:8080``) does not point
    internal clients at the wrong port when the platform runs on a different one.
    """
    try:
        global_settings = Configuration.get_global_settings_from_file(config_path)
    except (OSError, ValueError):
        return None
    platform_settings = global_settings.get("platform")
    if not isinstance(platform_settings, dict):
        return None
    base_url = platform_settings.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        return None
    try:
        parsed = urlparse(base_url)
    except ValueError:
        # Malformed value (e.g. an unterminated bracketed IPv6 like
        # ``http://[::1``). Fall back to the bind-derived default rather than
        # aborting startup — a bad config value should fail soft here.
        return None
    if not parsed.hostname:
        return None
    return parsed.scheme or "http", parsed.hostname


def _connect_host_for_internal_clients(host: str) -> str:
    """Translate a bind-address into a connectable address.

    Wildcard addresses (``0.0.0.0``, ``::``) are replaced with the
    corresponding loopback address so that internal HTTP clients (e.g.
    controllers, readiness probes) can actually reach the server.
    """
    stripped = host.strip("[]")
    if stripped in _IPV4_WILDCARDS:
        return _IPV4_LOOPBACK
    if stripped in _IPV6_WILDCARDS:
        return _IPV6_LOOPBACK
    return stripped


def _bracket_ipv6(host: str) -> str:
    """Bracket an IPv6 literal so it can be composed into ``<host>:<port>``.

    Accepts an already-stripped host (no surrounding brackets) and wraps it in
    ``[...]`` when it is an IPv6 literal (contains ``:``); returns other hosts
    unchanged.
    """
    stripped = host.strip("[]")
    return f"[{stripped}]" if ":" in stripped else stripped
