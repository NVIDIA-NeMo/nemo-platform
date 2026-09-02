# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""In-sandbox Gym host HTTP runtime (``GET /health``, ``POST /rollouts/run``).

Started inside the OpenSandbox job image via ``RunHelper`` + ``RolloutCollectionHelper``.
Reads ``NMP_GYM_GLOBAL_CONFIG`` from bootstrap env (same JSON as colocated Gym, minus Ray GCS).

Imports only the standard library and ``nemo_gym`` at runtime: the module source is
injected verbatim into the sandbox image, where ``nemo_rl`` may not be importable.
"""

import asyncio
import json
import os
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

GYM_GLOBAL_CONFIG_ENV_KEY = "NMP_GYM_GLOBAL_CONFIG"
UV_CACHE_DIR_KEY = "uv_cache_dir"
UV_VENV_DIR_KEY = "uv_venv_dir"
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


def bootstrap_gym_host() -> tuple[Any, Any, Any]:
    """Start Gym servers and return (RunHelper, head_server_config, RolloutCollectionHelper)."""
    from nemo_gym.cli.env import RunHelper
    from nemo_gym.global_config import GlobalConfigDictParserConfig
    from nemo_gym.server_utils import BaseServerConfig
    from omegaconf import DictConfig

    global_config = _load_global_config_dict()
    _apply_uv_dirs(global_config)
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
