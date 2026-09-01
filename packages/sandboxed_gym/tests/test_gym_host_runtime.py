# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import socket
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock
from urllib.parse import urlsplit

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


def test_a_malformed_content_length_answers_instead_of_dropping_the_connection(ready_server):
    """`int()` on a junk header would raise out of `do_POST`, and the client would see a closed
    socket rather than the error envelope every other rejection path uses."""
    parsed = urlsplit(ready_server)
    with socket.create_connection((parsed.hostname, parsed.port), timeout=5) as sock:
        sock.sendall(
            b"POST /rollouts/run HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: not-a-number\r\n"
            b"\r\n"
        )
        raw = b""
        while b"}" not in raw:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk

    head, _, body = raw.partition(b"\r\n\r\n")
    assert b" 400 " in head.splitlines()[0]
    assert json.loads(body.decode())["error"]["code"] == "internal"


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
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *a, **k: "/opt/uv_cache\n")

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
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *a, **k: "/opt/uv_cache\n")

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


# --------------------------------------------------------------------------------------------
# Rollout attribution
#
# The question this answers: if an evaluation posts examples here instead of driving the `gym`
# CLI, can each result still be tied back to the task that produced it? Attribution by position
# is not enough -- a reordering misattributes every reward silently -- and attribution by
# `_ng_task_index` alone depends on Gym continuing to copy that field through.
# --------------------------------------------------------------------------------------------


class _IdentityStrippingHelper:
    """A helper whose results carry no index, i.e. Gym did not copy the caller's stamp through."""

    def run_examples(self, examples, head_server_config=None):
        async def _one(row):
            return row, {"response": {"output": []}, "reward": 0.5}

        return [_one(row) for row in examples]


class _IdentityPreservingHelper:
    """A helper whose results carry Gym's own indices, which must win over the row's."""

    def run_examples(self, examples, head_server_config=None):
        async def _one(row):
            return row, {"reward": 1.0, "_ng_task_index": 99, "_ng_rollout_index": 7}

        return [_one(row) for row in examples]


def test_results_are_attributable_when_gym_drops_the_caller_stamp():
    # Two examples with distinct indices: the failure this guards against is both results coming
    # back indistinguishable, which reads as success and scores the wrong task.
    examples = [
        {"agent_ref": {"name": "a"}, "_ng_task_index": 0},
        {"agent_ref": {"name": "b"}, "_ng_task_index": 1},
    ]

    results = runtime.run_rollouts_sync(examples, MagicMock(), _IdentityStrippingHelper())

    assert [result["_ng_task_index"] for result in results] == [0, 1]


def test_an_index_gym_supplies_is_not_overwritten_by_the_row():
    # Gym assigns `_ng_rollout_index` itself, per attempt. Ours is a fallback, never an override:
    # clobbering Gym's would collapse repeats of one task onto a single trial.
    examples = [{"agent_ref": {"name": "a"}, "_ng_task_index": 3, "_ng_rollout_index": 0}]

    results = runtime.run_rollouts_sync(examples, MagicMock(), _IdentityPreservingHelper())

    assert results[0]["_ng_task_index"] == 99
    assert results[0]["_ng_rollout_index"] == 7


def test_examples_without_identity_are_passed_through_unchanged():
    # Customizer posts examples with no `_ng_*` fields at all; nothing may be invented for them.
    results = runtime.run_rollouts_sync([{"agent_ref": {"name": "a"}}], MagicMock(), _IdentityStrippingHelper())

    assert results[0] == {"response": {"output": []}, "reward": 0.5}


def test_identity_survives_the_http_boundary(ready_server):
    """The path an eval would actually take: POST examples, read attributable results back."""
    import urllib.request

    payload = json.dumps(
        {
            "examples": [
                {"agent_ref": {"name": "a"}, "_ng_task_index": 4},
                {"agent_ref": {"name": "b"}, "_ng_task_index": 9},
            ]
        }
    ).encode()
    runtime.Handler.max_request_bytes = 8192
    req = urllib.request.Request(
        f"{ready_server}/rollouts/run",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())

    assert [result["_ng_task_index"] for result in body["results"]] == [4, 9]


@pytest.mark.parametrize("result", ["not-a-dict", None, 42])
def test_a_non_mapping_result_is_left_alone(result):
    # The helper's result shape is Gym's to define; this must not assume it is always a dict.
    assert runtime._with_row_identity(result, {"_ng_task_index": 1}) is result
