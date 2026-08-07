# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest

from sandboxed_gym.runtime import gym_host_runtime as runtime


class _FakeRolloutHelper:
    def run_examples(self, examples, head_server_config=None):
        async def _one(row):
            return row, {"response": {"output": []}, "reward": 0.0}

        return [_one(row) for row in examples]


@pytest.fixture
def ready_server():
    runtime._READY = True
    runtime._RUN_HELPER = MagicMock()
    runtime._HEAD_SERVER_CONFIG = MagicMock()
    runtime._ROLLOUT_HELPER = _FakeRolloutHelper()
    runtime.Handler.max_request_bytes = 1024
    runtime.Handler.max_response_bytes = 4096

    server = HTTPServer(("127.0.0.1", 0), runtime.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        runtime._READY = False
        runtime._HEAD_SERVER_CONFIG = None
        runtime._ROLLOUT_HELPER = None


def test_health_not_ready():
    runtime._READY = False
    server = HTTPServer(("127.0.0.1", 0), runtime.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.error
        import urllib.request

        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
        assert exc.value.code == 503
        body = json.loads(exc.value.read().decode())
        assert body["status"] == "starting"
    finally:
        server.shutdown()
        server.server_close()


def test_health_ready(ready_server):
    import urllib.request

    with urllib.request.urlopen(f"{ready_server}/health", timeout=5) as resp:
        assert resp.status == 200
        assert json.loads(resp.read().decode()) == {"status": "ready"}


def test_rollouts_run_returns_results(ready_server):
    import urllib.request

    payload = json.dumps({"examples": [{"agent_ref": {"name": "a"}, "id": 1}]}).encode()
    req = urllib.request.Request(
        f"{ready_server}/rollouts/run",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    assert len(body["results"]) == 1
    assert body["results"][0]["reward"] == 0.0


def test_rollouts_run_rejects_oversize_request(ready_server):
    import urllib.error
    import urllib.request

    payload = b"x" * 2048
    req = urllib.request.Request(
        f"{ready_server}/rollouts/run",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 413
    err = json.loads(exc.value.read().decode())
    assert err["error"]["code"] == "payload_too_large"


def test_run_rollouts_sync_collects():
    helper = _FakeRolloutHelper()
    results = runtime.run_rollouts_sync(
        [{"agent_ref": {"name": "x"}}],
        MagicMock(),
        helper,
    )
    assert len(results) == 1


def test_apply_uv_dirs_sets_config_keys_in_container(monkeypatch):
    """Gym reads the CONFIG keys, not the env vars - the env alone gets overwritten."""
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.setenv("NEMO_GYM_VENV_DIR", "/opt/gym_venvs")
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(
        runtime.subprocess, "check_output", lambda *a, **k: "/opt/uv_cache\n"
    )

    config: dict = {}
    runtime._apply_uv_dirs(config)

    assert config[runtime.UV_CACHE_DIR_KEY] == "/opt/uv_cache"
    assert config[runtime.UV_VENV_DIR_KEY] == "/opt/gym_venvs"


def test_apply_uv_dirs_noop_outside_container(monkeypatch):
    monkeypatch.delenv("NRL_CONTAINER", raising=False)
    monkeypatch.delenv("NEMO_GYM_VENV_DIR", raising=False)

    config: dict = {}
    runtime._apply_uv_dirs(config)

    assert config == {}


def test_apply_uv_dirs_does_not_override_explicit_config(monkeypatch):
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.setenv("NEMO_GYM_VENV_DIR", "/opt/gym_venvs")
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(
        runtime.subprocess, "check_output", lambda *a, **k: "/opt/uv_cache\n"
    )

    config = {runtime.UV_CACHE_DIR_KEY: "/custom/cache"}
    runtime._apply_uv_dirs(config)

    assert config[runtime.UV_CACHE_DIR_KEY] == "/custom/cache"
    assert config[runtime.UV_VENV_DIR_KEY] == "/opt/gym_venvs"


def test_uv_cache_dir_prefers_the_configured_env_var(monkeypatch):
    """`uv cache dir` exits non-zero when the CWD's pyproject pins a conflicting
    [tool.uv] required-version - true in the nemo-platform image - so an explicit
    UV_CACHE_DIR must win without shelling out at all."""
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.setenv("UV_CACHE_DIR", "/home/ubuntu/.cache/uv")

    def _never(*a, **k):
        raise AssertionError("uv should not be invoked when UV_CACHE_DIR is set")

    monkeypatch.setattr(runtime.subprocess, "check_output", _never)

    assert runtime._uv_cache_dir() == "/home/ubuntu/.cache/uv"


def test_uv_cache_dir_returns_none_when_uv_unavailable(monkeypatch):
    """No env var and no usable `uv`: let Gym pick its own rather than crash."""
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)

    def _boom(*a, **k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(runtime.subprocess, "check_output", _boom)

    assert runtime._uv_cache_dir() is None
