# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""In-sandbox Gym host HTTP runtime (``GET /health``, ``POST /rollouts/run``).

Started inside the OpenSandbox job image via ``RunHelper`` + ``RolloutCollectionHelper``.
Reads ``NMP_GYM_GLOBAL_CONFIG`` from bootstrap env (same JSON as colocated Gym, minus Ray GCS).

Imports only the standard library, PyYAML, and ``nemo_gym`` at runtime: the module source
is injected verbatim into the sandbox image, where ``nemo_rl`` may not be importable.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from sandboxed_gym.environment_package import (
    ENVIRONMENT_MANIFEST_FILENAME,
    EnvironmentPackage,
    EnvironmentPackageError,
    WheelsV1Package,
    inspect_environment_components,
    inspect_environment_namespaces,
    load_environment_package,
    validate_environment_namespaces,
)

GYM_GLOBAL_CONFIG_ENV_KEY = "NMP_GYM_GLOBAL_CONFIG"
#: Set by the orchestrator when the caller supplied an explicit ``environment_path`` (a FileSet).
#: ``NMP_ENVIRONMENT_PATH`` is also the host's environment *mount*, so it is ``/job/environment``
#: for image-bundled Gym too; this flag is how a missing ``nemo-environment.yaml`` becomes a
#: FileSet error instead of a silent fallback to the image-shipped environment.
ENVIRONMENT_PACKAGE_REQUIRED_ENV_KEY = "NMP_ENVIRONMENT_PACKAGE_REQUIRED"
UV_CACHE_DIR_KEY = "uv_cache_dir"
UV_VENV_DIR_KEY = "uv_venv_dir"
# Writable /job/work subdirectory where wheels are installed for the running Gym host.
WHEELS_V1_INSTALL_SUBDIR = "wheels-v1-site-packages"
# uv setting that points Gym's per-server dependency resolver at the staged wheelhouse.
UV_FIND_LINKS_ENV_KEY = "UV_FIND_LINKS"
NEMO_GYM_EXTRA_ROOTS_ENV_KEY = "NEMO_GYM_EXTRA_ROOTS"
#: Which agent, resources server, and model to run. Gym has no schema for this key, so
#: the host pops it and rewrites ``config_paths`` before Gym parses the dict.
ENVIRONMENT_COMPONENT_SELECTION_CONFIG_KEY = "_nmp_environment_component_selection"
# Mirrors DEFAULT_GYM_PORT_RANGE_{LOW,HIGH} in nemo_rl.distributed.virtual_cluster.
DEFAULT_GYM_PORT_RANGE_LOW = 5000
DEFAULT_GYM_PORT_RANGE_HIGH = 5999

_DEFAULT_HTTP_PORT = 8080
_READY: bool = False
_RUN_HELPER: Any = None
_HEAD_SERVER_CONFIG: Any = None
_ROLLOUT_HELPER: Any = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _runtime_error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _load_global_config_dict() -> dict[str, Any]:
    raw = os.environ.get(GYM_GLOBAL_CONFIG_ENV_KEY, "").strip()
    if not raw:
        raise RuntimeError(f"{GYM_GLOBAL_CONFIG_ENV_KEY} is not set")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{GYM_GLOBAL_CONFIG_ENV_KEY} must be a JSON object")
    return parsed


def _free_port_in_range(low: int, high: int) -> int:
    for port in range(low, high + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("", port))
            except OSError:
                continue
            sock.listen(1)
            return port
    raise RuntimeError(f"no free port in range [{low}, {high}]")


def _allocate_head_server_port(global_config: dict[str, Any]) -> int:
    from nemo_gym.server_utils import HEAD_SERVER_KEY_NAME

    low = int(global_config.get("port_range_low", DEFAULT_GYM_PORT_RANGE_LOW))
    high = int(global_config.get("port_range_high", DEFAULT_GYM_PORT_RANGE_HIGH))
    port = _free_port_in_range(low, high)
    global_config[HEAD_SERVER_KEY_NAME] = {"host": "0.0.0.0", "port": port}
    return port


def _create_rollout_helper() -> Any:
    from nemo_gym.rollout_collection import RolloutCollectionHelper

    return RolloutCollectionHelper()


def _uv_cache_dir() -> str | None:
    """Cache dir uv resolves to here, or None to let Gym pick its own.

    Mirrors ``nemo_rl.environments.nemo_gym.get_nemo_gym_uv_cache_dir``, duplicated
    because this module must stay importable without ``nemo_rl``.
    """
    if not os.environ.get("NRL_CONTAINER"):
        return None
    # Prefer the explicit env var. The container image sets it, and it sidesteps
    # `uv cache dir`, which exits non-zero whenever the working directory's
    # pyproject.toml pins a [tool.uv] required-version that disagrees with the uv on
    # PATH - true in the nemo-platform image, whose WORKDIR is the platform workspace.
    configured = os.environ.get("UV_CACHE_DIR")
    if configured:
        return configured
    try:
        resolved = subprocess.check_output(["uv", "cache", "dir"], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return resolved or None


def _apply_uv_dirs(global_config: dict[str, Any]) -> None:
    """Point Gym at the image-baked uv cache / venv dirs.

    The colocated path does this in ``NemoGym._spinup``, but the sandboxed path returns
    before it, so the host applies it here from the sandbox's own environment. These must
    land in the CONFIG, not just the environment: Gym overwrites ``UV_CACHE_DIR`` from the
    config key, so without it Gym falls back to ``<Gym>/cache/uv`` in the read-only image
    tree and every per-app server dies with EACCES.
    """
    cache_dir = _uv_cache_dir()
    if cache_dir:
        global_config.setdefault(UV_CACHE_DIR_KEY, cache_dir)
    venv_dir = os.environ.get("NEMO_GYM_VENV_DIR")
    if venv_dir:
        global_config.setdefault(UV_VENV_DIR_KEY, venv_dir)


def _environment_package_required() -> bool:
    """Whether the mounted environment path must be a valid FileSet package.

    The host always mounts something at ``NMP_ENVIRONMENT_PATH`` (typically ``/job/environment``).
    Image-bundled Gym has no ``nemo-environment.yaml`` there. FileSet-backed runs do, and must
    fail closed if it is missing rather than starting against the image. The orchestrator sets
    this only when serve config carried an explicit ``environment_path``.
    """
    return os.environ.get(ENVIRONMENT_PACKAGE_REQUIRED_ENV_KEY, "").strip().lower() in {"1", "true", "yes"}


def _load_runtime_environment_package(
    environment_path: str,
    *,
    required: bool,
) -> EnvironmentPackage | None:
    """Load a mounted package while preserving manifest-free bundled environments."""
    if not environment_path:
        if required:
            raise RuntimeError("A Gym environment package is required, but NMP_ENVIRONMENT_PATH is empty")
        return None

    manifest_path = os.path.join(environment_path, ENVIRONMENT_MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        if required:
            raise RuntimeError(f"Gym environment package is missing required manifest: {manifest_path}")
        return None

    try:
        package = load_environment_package(environment_path)
    except EnvironmentPackageError as exc:
        raise RuntimeError(f"Invalid Gym environment package at {environment_path}: {exc}") from exc
    return package


def _install_wheels_v1_dependencies(package: EnvironmentPackage | None, work_path: str) -> None:
    """Install a wheels-v1 environment's vendored dependencies, with no package-index access.

    Other package formats are a no-op. When the validated package is ``wheels-v1``, every wheel
    under its wheelhouse is installed into the writable work mount, so nothing is fetched from a
    package index during this installation.

    The wheels are installed into the writable work directory instead of an existing virtualenv.
    ``PYTHONPATH`` exposes them to Gym's child processes, while ``sys.path`` exposes them to the
    already-running host process.
    """
    if not isinstance(package, WheelsV1Package):
        return

    wheels_dir = str(package.wheelhouse_path)

    wheels_install_dir = os.path.join(work_path, WHEELS_V1_INSTALL_SUBDIR)
    os.makedirs(wheels_install_dir, exist_ok=True)

    # --target keeps mutable packages under the writable work mount. --only-binary closes the
    # source-distribution path opened by --find-links, including for transitive dependencies.
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            wheels_install_dir,
            "--no-index",
            "--only-binary",
            ":all:",
            "--find-links",
            wheels_dir,
        ]
        + [str(wheel) for wheel in package.wheel_files],
        check=True,
    )

    # Gym creates a private venv for each agent and resource server from that component's
    # requirements.txt. Prefer the staged component wheels while retaining package-index fallback
    # for image-owned Gym and its core dependencies.
    os.environ[UV_FIND_LINKS_ENV_KEY] = wheels_dir

    # Gym starts agent and resource servers as child Python processes. Prepend the wheel target so
    # those processes can import the environment's vendored dependencies.
    existing_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = (
        os.pathsep.join((wheels_install_dir, existing_pythonpath)) if existing_pythonpath else wheels_install_dir
    )

    # Updating PYTHONPATH does not change the current interpreter's `sys.path`. Prepend the wheel
    # target so the host can import wheel-only packages, with the staged environment taking
    # precedence over packages baked into the runtime image.
    if wheels_install_dir not in sys.path:
        sys.path.insert(0, wheels_install_dir)


def _prepend_environment_search_root(environment_root: str) -> None:
    """Search the mounted environment package before Gym's built-in paths.

    Gym looks up config files in ``NEMO_GYM_EXTRA_ROOTS`` first. If the package is
    not at the front of that list, Gym loads the image's agent or resources server
    instead, and the job scores the wrong environment. Any extra roots already set
    stay after the package so they still work as backups.
    """
    existing = [root for root in os.environ.get(NEMO_GYM_EXTRA_ROOTS_ENV_KEY, "").split(os.pathsep) if root]
    roots = [environment_root, *existing]
    deduplicated = list(dict.fromkeys(roots))
    os.environ[NEMO_GYM_EXTRA_ROOTS_ENV_KEY] = os.pathsep.join(deduplicated)


def _configure_environment_package(
    global_config: dict[str, Any],
    package: EnvironmentPackage | None,
) -> None:
    """Build Gym's ``config_paths`` from the mounted package plus any built-in fallbacks.

    The eval job records which agent, resources server, and model to run in a temporary
    key. Here, we remove it and turn it into a ``config_paths`` list Gym expects.

    We start with the YAML files the package itself declared. If the package does not
    include the chosen agent or resources server, we add the matching built-in YAML
    from the image. If the package already has the agent or resources server, we skip
    the built-in copy — otherwise Gym would load two of the same name.

    A package that uses the same name for both an agent and a resources server is
    rejected here, before Gym starts and hits that collision itself.
    """
    selection = global_config.pop(ENVIRONMENT_COMPONENT_SELECTION_CONFIG_KEY, None)
    if package is None:
        if selection is not None:
            raise RuntimeError("Gym component selection was supplied without an environment package")
        return
    if not isinstance(selection, dict):
        raise RuntimeError("A mounted environment package requires Gym component selection metadata")

    required_string_fields = (
        "agent_instance",
        "resources_server_instance",
        "resources_server_config",
        "model_config",
    )
    for field in required_string_fields:
        if not isinstance(selection.get(field), str) or not selection[field]:
            raise RuntimeError(f"Gym component selection requires a non-empty {field!r}")
    # Optional: leave this unset when the package already ships the agent.
    agent_config = selection.get("agent_config")
    if agent_config is not None and (not isinstance(agent_config, str) or not agent_config):
        raise RuntimeError("Gym component selection agent_config must be a non-empty string or null")

    try:
        components = inspect_environment_components(package)
        package_namespaces = inspect_environment_namespaces(package, components=components)
        validate_environment_namespaces(package_namespaces)
    except EnvironmentPackageError as exc:
        raise RuntimeError(f"Invalid Gym environment components: {exc}") from exc

    _prepend_environment_search_root(str(package.root))
    config_paths = [str(path) for path in package.config_paths]
    agent_instance = str(selection["agent_instance"])
    if agent_instance not in components.agents:
        if agent_config is None:
            raise RuntimeError(
                f"Environment package does not declare selected agent instance {agent_instance!r}, "
                "and no built-in agent_config fallback was supplied"
            )
        config_paths.append(agent_config)

    # Custom models are not allowed. Always load the image's model YAML.
    config_paths.append(str(selection["model_config"]))
    resources_server_instance = str(selection["resources_server_instance"])
    if resources_server_instance not in components.resources_servers:
        config_paths.append(str(selection["resources_server_config"]))

    global_config["config_paths"] = list(dict.fromkeys(config_paths))


def bootstrap_gym_host() -> tuple[Any, Any, Any]:
    """Start Gym's servers and return the helpers used to run rollouts.

    Wire the mounted package into ``config_paths`` and install its wheels before
    importing ``nemo_gym``. Gym reads extra search roots at import time, and child
    processes inherit ``PYTHONPATH`` from this process. Doing this work after the
    import would start the image's environment, or start the custom one without its
    dependencies.
    """
    global_config = _load_global_config_dict()
    _apply_uv_dirs(global_config)
    environment_package = _load_runtime_environment_package(
        os.environ.get("NMP_ENVIRONMENT_PATH", ""),
        required=_environment_package_required(),
    )
    _configure_environment_package(global_config, environment_package)
    _install_wheels_v1_dependencies(
        environment_package,
        os.environ.get("NMP_WORK_PATH", "/job/work"),
    )

    # Import after the package is wired in: Gym reads extra search roots at import time.
    from nemo_gym.cli.env import RunHelper
    from nemo_gym.global_config import GlobalConfigDictParserConfig
    from nemo_gym.server_utils import BaseServerConfig
    from omegaconf import DictConfig

    head_port = _allocate_head_server_port(global_config)

    run_helper = RunHelper()
    run_helper.start(
        GlobalConfigDictParserConfig(
            initial_global_config_dict=DictConfig(global_config),
            skip_load_from_cli=True,
            skip_load_from_dotenv=True,
        )
    )
    head_server_config = BaseServerConfig(host="127.0.0.1", port=head_port)
    rollout_helper = _create_rollout_helper()
    return run_helper, head_server_config, rollout_helper


#: Rollout identity a caller stamps onto its examples. NeMo-Gym honours a pre-supplied
#: ``_ng_task_index`` and assigns ``_ng_rollout_index`` itself per attempt.
NG_TASK_INDEX = "_ng_task_index"
NG_ROLLOUT_INDEX = "_ng_rollout_index"


def _with_row_identity(result: Any, row: Any) -> Any:
    """Carry the example's rollout identity onto the result when it is not already there.

    ``run_examples`` yields each result alongside the row that produced it, and that pairing is the
    only attribution a caller gets for free. Gym normally copies ``_ng_task_index`` through -- it is
    the one caller-supplied field on the allowlist -- but a caller that has to *assume* that is one
    Gym change away from silently misattributing every reward, and a consumer joining on position
    instead is one reordering away from the same. Restoring the identity here makes the join a
    property of this host rather than of Gym's copy rules.

    Additive: a value Gym returned is never overwritten, so a result that already carries its own
    index is untouched and existing consumers see exactly the fields they saw before.
    """
    if not isinstance(result, dict) or not isinstance(row, dict):
        return result
    missing = {key: row[key] for key in (NG_TASK_INDEX, NG_ROLLOUT_INDEX) if key in row and result.get(key) is None}
    return {**result, **missing} if missing else result


async def _collect_rollout_results(
    examples: list[dict],
    head_server_config: Any,
    rollout_helper: Any,
) -> list[dict]:
    results: list[dict] = []
    for task in rollout_helper.run_examples(examples=examples, head_server_config=head_server_config):
        row, nemo_gym_result = await task
        results.append(_with_row_identity(nemo_gym_result, row))
    return results


def run_rollouts_sync(
    examples: list[dict],
    head_server_config: Any,
    rollout_helper: Any,
) -> list[dict]:
    return asyncio.run(_collect_rollout_results(examples, head_server_config, rollout_helper))


class Handler(BaseHTTPRequestHandler):
    max_request_bytes: int = 268_435_456
    max_response_bytes: int = 268_435_456

    def do_GET(self) -> None:
        if not self.path.startswith("/health"):
            self.send_response(404)
            self.end_headers()
            return
        if not _READY:
            body = json.dumps({"status": "starting"}).encode("utf-8")
            self.send_response(503)
        else:
            body = json.dumps({"status": "ready"}).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self.path.startswith("/rollouts/run"):
            self.send_response(404)
            self.end_headers()
            return
        if not _READY or _HEAD_SERVER_CONFIG is None or _ROLLOUT_HELPER is None:
            self._send_json(503, _runtime_error("bootstrap_failed", "Gym host not ready"))
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, _runtime_error("internal", "invalid Content-Length header"))
            return
        if length > self.max_request_bytes:
            self._send_json(
                413,
                _runtime_error(
                    "payload_too_large",
                    f"request body {length} exceeds max {self.max_request_bytes}",
                ),
            )
            return

        raw = self.rfile.read(length)
        try:
            request = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(
                400,
                _runtime_error("internal", "invalid JSON body"),
            )
            return

        examples = request.get("examples")
        if not isinstance(examples, list):
            self._send_json(
                400,
                _runtime_error("internal", "examples must be a list"),
            )
            return

        try:
            results = run_rollouts_sync(examples, _HEAD_SERVER_CONFIG, _ROLLOUT_HELPER)
        except Exception as exc:
            self._send_json(
                500,
                _runtime_error("internal", str(exc)),
            )
            return

        envelope = {
            "results": results,
            "job_id": os.environ.get("NMP_JOB_ID", ""),
            "environment_path": os.environ.get("NMP_ENVIRONMENT_PATH", ""),
            "work_path": os.environ.get("NMP_WORK_PATH", ""),
        }
        body = json.dumps(envelope).encode("utf-8")
        if len(body) > self.max_response_bytes:
            self._send_json(
                413,
                _runtime_error(
                    "payload_too_large",
                    f"response body {len(body)} exceeds max {self.max_response_bytes}",
                ),
            )
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    global _READY, _RUN_HELPER, _HEAD_SERVER_CONFIG, _ROLLOUT_HELPER

    Handler.max_request_bytes = _env_int("NMP_MAX_REQUEST_BYTES", Handler.max_request_bytes)
    Handler.max_response_bytes = _env_int("NMP_MAX_RESPONSE_BYTES", Handler.max_response_bytes)

    _RUN_HELPER, _HEAD_SERVER_CONFIG, _ROLLOUT_HELPER = bootstrap_gym_host()
    _READY = True

    port = _env_int("NMP_RUNTIME_HTTP_PORT", _DEFAULT_HTTP_PORT)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
