# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""In-sandbox Gym host HTTP runtime (``GET /health``, ``POST /rollouts/run``).

Started inside the OpenSandbox job image via ``RunHelper`` + ``RolloutCollectionHelper``.
Reads ``NMP_GYM_GLOBAL_CONFIG`` from bootstrap env (same JSON as colocated Gym, minus Ray GCS).

Imports only the standard library, PyYAML, and ``nemo_gym`` at runtime: the module source
is injected verbatim into the sandbox image, where ``nemo_rl`` may not be importable.
"""

import asyncio
import concurrent.futures
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sandboxed_gym.environment_package import (
    ENVIRONMENT_MANIFEST_FILENAME,
    EnvironmentPackage,
    EnvironmentPackageError,
    WheelsV1Package,
    load_environment_package,
    require_supported_runtime_format,
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
# Mirrors DEFAULT_GYM_PORT_RANGE_{LOW,HIGH} in nemo_rl.distributed.virtual_cluster.
DEFAULT_GYM_PORT_RANGE_LOW = 5000
DEFAULT_GYM_PORT_RANGE_HIGH = 5999

_DEFAULT_HTTP_PORT = 8080
_READY: bool = False
_RUN_HELPER: Any = None
_HEAD_SERVER_CONFIG: Any = None
_ROLLOUT_HELPER: Any = None
_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
_EVENT_LOOP_LOCK = threading.Lock()

#: The sandbox proxy gives up on a request whose first byte has not arrived within 180s, a cap its
#: config does not expose, and a batch routinely outlasts that. Whitespace is a valid JSON prefix,
#: so writing it while the work runs costs the reader nothing and keeps every hop's timer alive.
_HEARTBEAT_INTERVAL_S = 15.0
#: With no hop left to time a rollout out, the host has to be what gives up: a wedged batch would
#: otherwise heartbeat until the sandbox's ttl_s.
ROLLOUT_DEADLINE_ENV_KEY = "NMP_ROLLOUT_DEADLINE_S"
_DEFAULT_ROLLOUT_DEADLINE_S = 30 * 60.0
# Bounded so a deeply recursive failure cannot produce an oversized error response.
_TRACEBACK_FRAMES = 20
_MAX_TRACEBACK_CHARS = 8_000


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


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
            raise RuntimeError("a Gym environment package is required, but NMP_ENVIRONMENT_PATH is empty")
        return None

    manifest_path = os.path.join(environment_path, ENVIRONMENT_MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        if required:
            raise RuntimeError(f"Gym environment package is missing required manifest: {manifest_path}")
        return None

    try:
        package = load_environment_package(environment_path)
        require_supported_runtime_format(package)
    except EnvironmentPackageError as exc:
        raise RuntimeError(f"invalid Gym environment package at {environment_path}: {exc}") from exc
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


def bootstrap_gym_host() -> tuple[Any, Any, Any]:
    """Start Gym servers and return (RunHelper, head_server_config, RolloutCollectionHelper)."""
    global_config = _load_global_config_dict()
    _apply_uv_dirs(global_config)
    environment_package = _load_runtime_environment_package(
        os.environ.get("NMP_ENVIRONMENT_PATH", ""),
        required=_environment_package_required(),
    )
    _install_wheels_v1_dependencies(
        environment_package,
        os.environ.get("NMP_WORK_PATH", "/job/work"),
    )

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


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide event loop every rollout request runs on.

    One loop per process, not one per request: Gym's shared HTTP client binds to the loop that
    created it, so a per-request loop would leave the next request pointing at a closed one.
    """
    global _EVENT_LOOP
    with _EVENT_LOOP_LOCK:
        if _EVENT_LOOP is None:
            _EVENT_LOOP = asyncio.new_event_loop()
            threading.Thread(target=_EVENT_LOOP.run_forever, name="gym-host-event-loop", daemon=True).start()
        return _EVENT_LOOP


def submit_rollouts(
    examples: list[dict],
    head_server_config: Any,
    rollout_helper: Any,
) -> concurrent.futures.Future[list[dict]]:
    """Start ``examples`` on the shared loop and return without waiting.

    Handing back a future rather than the results is what lets the handler answer before the work
    finishes, so a long batch does not look to the proxy like an unresponsive server.
    """
    # Handler threads hand work to the one loop, so concurrent /rollouts/run calls interleave on
    # it rather than each running a loop of its own.
    return asyncio.run_coroutine_threadsafe(
        _collect_rollout_results(examples, head_server_config, rollout_helper),
        _ensure_event_loop(),
    )


def run_rollouts_sync(
    examples: list[dict],
    head_server_config: Any,
    rollout_helper: Any,
) -> list[dict]:
    return submit_rollouts(examples, head_server_config, rollout_helper).result()


class Handler(BaseHTTPRequestHandler):
    max_request_bytes: int = 268_435_456
    max_response_bytes: int = 268_435_456
    heartbeat_interval_s: float = _HEARTBEAT_INTERVAL_S
    rollout_deadline_s: float = _DEFAULT_ROLLOUT_DEADLINE_S

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

        # The only progress signal this process emits: log_message is silenced below, and both Gym
        # servers filter their own 200s.
        print(f"gym-host: rollouts/run <- {len(examples)} example(s)", flush=True)
        started = time.monotonic()
        future = submit_rollouts(examples, _HEAD_SERVER_CONFIG, _ROLLOUT_HELPER)

        # Committed to 200 before the work is done, so the first byte leaves immediately and no hop
        # can mistake a long batch for a dead one. Everything judgeable from the request alone was
        # rejected with a real status above; failures from here travel in the body as
        # {"error": ...}, which the caller already treats as fatal. No Content-Length: the body is
        # delimited by the close that `Connection: close` promises, which is what allows the
        # heartbeats below to precede a payload of unknown length.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(self._await_results(future, started))

    def _await_results(self, future: concurrent.futures.Future[list[dict]], started: float) -> bytes:
        """Wait for ``future``, heartbeating while it runs, and return the body to send.

        Returns an error envelope rather than raising: the status line is already on the wire by
        the time this is called, so a failure can only be reported in the body.
        """
        deadline = started + self.rollout_deadline_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                future.cancel()
                detail = f"rollout exceeded the host deadline of {self.rollout_deadline_s:g}s and was abandoned"
                print(f"gym-host: rollouts/run failed: {detail}", flush=True)
                return self._error_body("deadline_exceeded", detail)

            # wait() rather than result(timeout=...): a rollout is free to raise TimeoutError of
            # its own, which is not this loop's tick.
            done, _ = concurrent.futures.wait([future], timeout=min(self.heartbeat_interval_s, remaining))
            if not done:
                try:
                    self.wfile.write(b" ")
                    self.wfile.flush()
                except OSError as exc:
                    # The caller is gone. Nothing will read this batch, so stop paying for it:
                    # cancelling the future propagates to the collector task on the shared loop.
                    # Rollouts Gym has already started keep running until they finish -- they are
                    # its tasks, not ours, and the deadline above is what bounds them.
                    future.cancel()
                    print(
                        f"gym-host: rollouts/run abandoned, the caller disconnected: {exc}",
                        flush=True,
                    )
                    raise
                continue

            try:
                results = future.result()
            except Exception as exc:
                # Returned to the caller: this process's stdout never reaches the job.
                detail = traceback.format_exc(limit=_TRACEBACK_FRAMES)
                print(f"gym-host: rollouts/run failed: {detail}", flush=True)
                return self._error_body("internal", f"{type(exc).__name__}: {exc}\n{detail[-_MAX_TRACEBACK_CHARS:]}")
            break

        print(
            f"gym-host: rollouts/run -> {len(results)} result(s) in {time.monotonic() - started:.1f}s",
            flush=True,
        )
        envelope = {
            "results": results,
            "job_id": os.environ.get("NMP_JOB_ID", ""),
            "environment_path": os.environ.get("NMP_ENVIRONMENT_PATH", ""),
            "work_path": os.environ.get("NMP_WORK_PATH", ""),
        }
        body = json.dumps(envelope).encode("utf-8")
        if len(body) > self.max_response_bytes:
            return self._error_body(
                "payload_too_large",
                f"response body {len(body)} exceeds max {self.max_response_bytes}; "
                f"lower sandbox.rollout_chunk_size or raise sandbox.max_response_bytes",
            )
        return body

    def _error_body(self, code: str, message: str) -> bytes:
        return json.dumps(_runtime_error(code, message)).encode("utf-8")

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
    # Set from the caller's rollout_timeout_s. This, not that timeout, is what actually bounds a
    # batch: the client's is a per-read socket timeout, and the heartbeat keeps resetting it.
    Handler.rollout_deadline_s = _env_float(ROLLOUT_DEADLINE_ENV_KEY, Handler.rollout_deadline_s)

    _ensure_event_loop()
    _RUN_HELPER, _HEAD_SERVER_CONFIG, _ROLLOUT_HELPER = bootstrap_gym_host()
    _READY = True

    port = _env_int("NMP_RUNTIME_HTTP_PORT", _DEFAULT_HTTP_PORT)
    # Threaded so chunked rollouts overlap and /health stays answerable mid-batch.
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
