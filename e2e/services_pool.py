# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared E2E services-pool implementation used by pytest fixtures."""

import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from _pytest.nodes import Node
from nmp.testing.e2e.config import deep_merge

logger = logging.getLogger(__name__)
_E2E_HARNESS_DEBUG = os.environ.get("E2E_HARNESS_DEBUG") == "1"

_HEALTH_TIMEOUT = 60
_HEALTH_POLL_INTERVAL = 1.0
_AUTH_READY_TIMEOUT = 60
_E2E_ADMIN_EMAIL = "admin@example.com"
_E2E_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_E2E_PLATFORM_CONFIG = _E2E_REPO_ROOT / "packages/nmp_platform/config/local.yaml"


def admin_headers() -> dict[str, str]:
    return {
        "X-NMP-Principal-Id": _E2E_ADMIN_EMAIL,
        "X-NMP-Principal-Email": _E2E_ADMIN_EMAIL,
    }


@dataclass(frozen=True)
class ServicesPoolKey:
    config_hash: str


@dataclass
class RunningServices:
    url: str
    log_path: Path | None
    proc: subprocess.Popen[Any] | None
    config_path: Path | None
    auth_enabled: bool = False
    key: ServicesPoolKey | None = None


@dataclass(frozen=True)
class ModuleConfigState:
    module_id: str
    key: ServicesPoolKey
    config_path: Path | None
    config_data: dict[str, Any]
    config_layers: tuple[str, ...]
    auth_enabled: bool


class E2EServicesPool:
    """Central manager for config-hash-based E2E service pooling."""

    def __init__(self) -> None:
        self._tmp_path_factory: pytest.TempPathFactory | None = None
        self._module_states: dict[str, ModuleConfigState] = {}
        self._remaining_modules_by_key: dict[ServicesPoolKey, set[str]] = {}
        self._running_by_key: dict[ServicesPoolKey, RunningServices] = {}
        self._active_service_key_by_module: dict[str, ServicesPoolKey] = {}
        self._generated_config_dir: Path | None = None
        self._log_dir: Path | None = None

    @staticmethod
    def _log_debug(message: str, **extra: Any) -> None:
        if _E2E_HARNESS_DEBUG:
            logger.info(message, extra=extra)

    def bind_tmp_path_factory(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        if self._tmp_path_factory is None:
            self._tmp_path_factory = tmp_path_factory

    def register_collected_items(self, items: list[pytest.Item]) -> None:
        seen_modules: set[str] = set()
        for item in items:
            module = item.getparent(pytest.Module)
            if module is None or module.nodeid in seen_modules:
                continue
            seen_modules.add(module.nodeid)
            self._ensure_module_registered(module)

    def acquire_for_module(self, module: pytest.Module) -> RunningServices:
        self._ensure_module_registered(module)
        state = self._module_states[module.nodeid]
        external_url = os.environ.get("NMP_BASE_URL")
        if external_url:
            return RunningServices(
                url=external_url,
                log_path=None,
                proc=None,
                config_path=None,
                auth_enabled=state.auth_enabled,
            )
        if state.config_path is None:
            state = self._materialize_config_path(state)
            self._module_states[module.nodeid] = state
        assert state.config_path is not None
        services = self._running_by_key.get(state.key)
        if services is None:
            log_path = self._get_log_dir() / f"services-{state.key.config_hash}-{uuid.uuid4().hex[:8]}.log"
            services = _start_services(state.config_path, state.config_data, state.key.config_hash, log_path)
            self._running_by_key[state.key] = services
        previous_key = self._active_service_key_by_module.get(module.nodeid)
        if previous_key is not None and previous_key != state.key:
            logger.error(
                "E2E module rebound to a different services pool key",
                extra={
                    "e2e_module": module.nodeid,
                    "previous_config_hash": previous_key.config_hash,
                    "new_config_hash": state.key.config_hash,
                    "new_url": services.url,
                    "new_pid": services.proc.pid if services.proc is not None else None,
                },
            )
        self._active_service_key_by_module[module.nodeid] = state.key
        self._log_debug("E2E services acquire", **self.describe_module_binding(module.nodeid, services))
        return services

    def release_for_module(self, module: pytest.Module) -> None:
        if os.environ.get("NMP_BASE_URL"):
            return
        state = self._module_states.get(module.nodeid)
        if state is None:
            return
        remaining = self._remaining_modules_by_key.get(state.key)
        if remaining is None or module.nodeid not in remaining:
            return
        remaining.remove(module.nodeid)
        self._log_debug(
            "E2E services release",
            **{
                **self.describe_module_binding(module.nodeid),
                "remaining_modules_for_hash": sorted(remaining),
            },
        )
        if remaining:
            return
        self._remaining_modules_by_key.pop(state.key, None)
        self._active_service_key_by_module.pop(module.nodeid, None)
        services = self._running_by_key.pop(state.key, None)
        if services is not None:
            self._terminate_services(services)

    def shutdown_all(self) -> None:
        for services in list(self._running_by_key.values()):
            self._terminate_services(services)
        self._running_by_key.clear()
        self._remaining_modules_by_key.clear()

    def _ensure_module_registered(self, module: pytest.Module) -> None:
        if module.nodeid in self._module_states:
            return
        resolved_paths, config_data = _load_effective_e2e_config_from_node(module)
        key = _services_pool_key(_canonical_config_hash(config_data))
        auth_enabled = _e2e_auth_enabled(config_data)
        self._module_states[module.nodeid] = ModuleConfigState(
            module_id=module.nodeid,
            key=key,
            config_path=None,
            config_data=config_data,
            config_layers=tuple(str(path) for path in resolved_paths),
            auth_enabled=auth_enabled,
        )
        self._remaining_modules_by_key.setdefault(key, set()).add(module.nodeid)
        self._log_debug(
            "Registered E2E module config",
            e2e_module=module.nodeid,
            config_hash=key.config_hash,
            config_layers=list(self._module_states[module.nodeid].config_layers),
            auth_enabled=auth_enabled,
        )

    def _materialize_config_path(self, state: ModuleConfigState) -> ModuleConfigState:
        data_dir = e2e_services_data_dir(self._get_log_dir(), state.key.config_hash)
        rendered_config_data = with_e2e_instance_paths(state.config_data, data_dir)
        rendered_config = yaml.safe_dump(rendered_config_data, default_flow_style=False, sort_keys=True)
        config_path = self._get_generated_config_dir() / f"platform-{state.key.config_hash}.yaml"
        if not config_path.exists():
            config_path.write_text(rendered_config)
            self._log_debug(
                "Materialized generated E2E config",
                e2e_module=state.module_id,
                config_hash=state.key.config_hash,
                config_path=str(config_path),
            )
        return ModuleConfigState(
            module_id=state.module_id,
            key=state.key,
            config_path=config_path,
            config_data=state.config_data,
            config_layers=state.config_layers,
            auth_enabled=state.auth_enabled,
        )

    def _get_generated_config_dir(self) -> Path:
        if self._generated_config_dir is None:
            self._generated_config_dir = self._get_log_dir() / "generated-configs"
            self._generated_config_dir.mkdir(parents=True, exist_ok=True)
        return self._generated_config_dir

    def _get_log_dir(self) -> Path:
        if self._tmp_path_factory is None:
            raise RuntimeError("E2E services pool used before tmp_path_factory was bound")
        if self._log_dir is None:
            self._log_dir = _services_log_dir(self._tmp_path_factory)
        return self._log_dir

    @staticmethod
    def _terminate_services(services: RunningServices) -> None:
        if services.proc is None:
            return
        if services.proc.poll() is not None:
            E2EServicesPool._log_debug(
                "Skipping E2E services terminate for already-exited process",
                config_hash=services.key.config_hash if services.key is not None else None,
                pid=services.proc.pid,
                returncode=services.proc.returncode,
                url=services.url,
            )
            return
        logger.info("Terminating nemo services (pid %d)", services.proc.pid)
        services.proc.terminate()
        try:
            services.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Process %d did not exit after SIGTERM, sending SIGKILL", services.proc.pid)
            services.proc.kill()
            services.proc.wait(timeout=5)

    def describe_module_binding(
        self,
        module_id: str,
        services: RunningServices | None = None,
    ) -> dict[str, Any]:
        state = self._module_states[module_id]
        details: dict[str, Any] = {
            "e2e_module": module_id,
            "config_hash": state.key.config_hash,
            "auth_enabled": state.auth_enabled,
            "config_layers": list(state.config_layers),
            "config_path": str(state.config_path) if state.config_path is not None else None,
        }
        if services is not None:
            details.update(
                {
                    "service_url": services.url,
                    "service_pid": services.proc.pid if services.proc is not None else None,
                    "service_log_path": str(services.log_path) if services.log_path is not None else None,
                }
            )
        return details


def _services_log_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    log_dir = os.environ.get("E2E_SERVICES_LOG_DIR")
    if log_dir:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return tmp_path_factory.mktemp("e2e-services-logs")


def _resolve_e2e_config_layers_from_node(node: Node) -> list[str | dict[str, Any]]:
    marker = node.get_closest_marker("e2e_config")
    if marker is None or not marker.args:
        return [str(_DEFAULT_E2E_PLATFORM_CONFIG)]
    layers: list[str | dict[str, Any]] = []
    for layer in marker.args:
        if isinstance(layer, (str, dict)):
            layers.append(layer)
            continue
        raise pytest.UsageError("pytest.mark.e2e_config arguments must be strings or dicts")
    return layers


def _resolve_config_path(config_ref: str) -> Path:
    candidate = Path(config_ref)
    if not candidate.is_absolute():
        candidate = _E2E_REPO_ROOT / config_ref
    return candidate.resolve()


def _normalize_config(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_config(value[key], (*path, key)) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_normalize_config(item, path) for item in value]
        if path == ("jobs", "executors"):
            return sorted(
                normalized,
                key=lambda item: (
                    item.get("provider", "") if isinstance(item, dict) else "",
                    item.get("profile", "") if isinstance(item, dict) else "",
                    item.get("backend", "") if isinstance(item, dict) else "",
                    json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
                ),
            )
        return normalized
    return value


def _canonical_config_hash(config_data: dict[str, Any]) -> str:
    normalized = _normalize_config(config_data)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _load_effective_e2e_config_from_node(node: Node) -> tuple[list[Path], dict[str, Any]]:
    effective_config: dict[str, Any] = {}
    resolved_paths: list[Path] = []

    for layer in _resolve_e2e_config_layers_from_node(node):
        if isinstance(layer, str):
            config_path = _resolve_config_path(layer)
            if not config_path.is_file():
                raise pytest.UsageError(f"E2E platform config not found: {config_path}")
            layer_config = yaml.safe_load(config_path.read_text()) or {}
            resolved_paths.append(config_path)
        else:
            layer_config = layer
        effective_config = deep_merge(effective_config, layer_config)

    return resolved_paths, _normalize_config(effective_config)


def e2e_services_data_dir(log_dir: Path, config_hash: str) -> Path:
    """Return the persistent data directory for one pooled services instance."""
    return log_dir / f"data-{config_hash}"


def with_e2e_instance_paths(config_data: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    """Return config data with per-instance filesystem paths rooted under ``data_dir``."""
    rendered = deepcopy(config_data)
    subprocess_working_dir = str(data_dir / "subprocess-jobs")
    files_root = str(data_dir / "files")

    jobs = rendered.get("jobs")
    if isinstance(jobs, dict):
        executors = jobs.get("executors")
        if isinstance(executors, list):
            for executor in executors:
                if not isinstance(executor, dict):
                    continue
                if executor.get("provider") != "subprocess":
                    continue
                config = executor.setdefault("config", {})
                if isinstance(config, dict):
                    config["working_directory"] = subprocess_working_dir

        executor_defaults = jobs.get("executor_defaults")
        if isinstance(executor_defaults, dict):
            subprocess_defaults = executor_defaults.get("subprocess")
            if isinstance(subprocess_defaults, dict):
                subprocess_defaults["working_directory"] = subprocess_working_dir

    files = rendered.get("files")
    if isinstance(files, dict):
        default_storage_config = files.get("default_storage_config")
        if isinstance(default_storage_config, dict) and default_storage_config.get("type") == "local":
            default_storage_config["path"] = files_root

    return rendered


def e2e_services_env(config_path: Path, data_dir: Path) -> dict[str, str]:
    """Environment for the ``nemo services run`` child process."""
    env = os.environ.copy()
    env["NMP_SEED_ON_STARTUP"] = "true"
    env["NMP_INFERENCE_GATEWAY_MOCK_PROVIDER_PREFIX"] = "igw-mock-"
    env["NMP_CONFIG_FILE_PATH"] = str(config_path)
    env["NMP_CONFIG_WARNINGS_DISABLED"] = "1"
    env["NMP_DATA_DIR"] = str(data_dir)
    return env


def _e2e_auth_enabled(config_data: dict[str, Any]) -> bool:
    auth_cfg = config_data.get("auth")
    return isinstance(auth_cfg, dict) and bool(auth_cfg.get("enabled", False))


def _services_pool_key(config_hash: str) -> ServicesPoolKey:
    return ServicesPoolKey(config_hash=config_hash)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _process_exited(proc: subprocess.Popen[Any]) -> bool:
    return proc.poll() is not None


def _wait_for_healthy(url: str, proc: subprocess.Popen[Any], timeout: float = _HEALTH_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _process_exited(proc):
            return False
        try:
            resp = httpx.get(f"{url}/status", timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        if _process_exited(proc):
            return False
        time.sleep(_HEALTH_POLL_INTERVAL)
    return False


def _wait_for_auth_ready(url: str, proc: subprocess.Popen[Any], timeout: float = _AUTH_READY_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _process_exited(proc):
            return False
        probe_name = f"auth-probe-{uuid.uuid4().hex[:8]}"
        entity_name = f"auth-probe-entity-{uuid.uuid4().hex[:8]}"
        try:
            create_resp = httpx.post(
                f"{url}/apis/entities/v2/workspaces",
                json={"name": probe_name},
                headers=admin_headers(),
                timeout=5.0,
            )
            if create_resp.status_code != 201:
                if _process_exited(proc):
                    return False
                time.sleep(_HEALTH_POLL_INTERVAL)
                continue

            entity_resp = httpx.post(
                f"{url}/apis/entities/v2/workspaces/{probe_name}/entities/e2e-auth-probe",
                json={"name": entity_name, "data": {"ready": True}},
                headers=admin_headers(),
                timeout=5.0,
            )
            if entity_resp.status_code != 201:
                httpx.delete(
                    f"{url}/apis/entities/v2/workspaces/{probe_name}",
                    headers=admin_headers(),
                    timeout=5.0,
                )
                time.sleep(_HEALTH_POLL_INTERVAL)
                continue

            httpx.delete(
                f"{url}/apis/entities/v2/workspaces/{probe_name}/entities/e2e-auth-probe/{entity_name}",
                headers=admin_headers(),
                timeout=5.0,
            )
            httpx.delete(
                f"{url}/apis/entities/v2/workspaces/{probe_name}",
                headers=admin_headers(),
                timeout=5.0,
            )
            return True
        except httpx.RequestError as exc:
            logger.debug("Auth readiness probe failed; will retry: %s", exc)
        if _process_exited(proc):
            return False
        time.sleep(_HEALTH_POLL_INTERVAL)
    return False


def _start_services(
    config_path: Path, config_data: dict[str, Any], config_hash: str, log_path: Path
) -> RunningServices:
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    nemo_bin = str(Path(sys.executable).parent / "nemo")
    args = [
        nemo_bin,
        "services",
        "run",
        "--service-group",
        "all",
        "--controller-group",
        "all",
        "--port",
        str(port),
    ]
    data_dir = e2e_services_data_dir(log_path.parent, config_hash)
    data_dir.mkdir(parents=True, exist_ok=True)
    env = e2e_services_env(config_path, data_dir)

    logger.info("Starting nemo services on port %d with config %s", port, config_path)

    log_file = open(log_path, "w")
    try:
        proc = subprocess.Popen(args, stdout=log_file, stderr=subprocess.STDOUT, env=env)
    finally:
        log_file.close()

    if not _wait_for_healthy(url, proc):
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
        pytest.fail(
            f"nemo services run did not become healthy within {_HEALTH_TIMEOUT}s.\nlog:\n{log_path.read_text()}"
        )
    auth_enabled = _e2e_auth_enabled(config_data)
    if auth_enabled and not _wait_for_auth_ready(url, proc):
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
        pytest.fail(
            f"Platform auth seed did not become ready within {_AUTH_READY_TIMEOUT}s.\nlog:\n{log_path.read_text()}"
        )

    logger.info("Platform services ready on port %d (pid %d)", port, proc.pid)
    return RunningServices(
        url=url,
        log_path=log_path,
        proc=proc,
        config_path=config_path,
        auth_enabled=auth_enabled,
        key=_services_pool_key(config_hash),
    )
