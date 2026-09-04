# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import socket
import threading
from http.server import HTTPServer
from types import ModuleType
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
from sandboxed_gym.environment_package import WHEELS_V1_SUBDIR
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


# --------------------------------------------------------------------------------------------
# wheels-v1 dependency install
# --------------------------------------------------------------------------------------------


def _write_manifest(env_dir, **fields):
    import yaml

    fields.setdefault("config_paths", ["resources_servers/test/configs/test.yaml"])
    fields.setdefault("metadata", {"name": "test-environment"})
    for relative_path in fields["config_paths"]:
        config = env_dir / relative_path
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("test: {}\n", encoding="utf-8")
    manifest_path = env_dir / runtime.ENVIRONMENT_MANIFEST_FILENAME
    manifest_path.write_text(yaml.safe_dump(fields), encoding="utf-8")


def _load_composition_package(env_dir, *, agents=(), resources_servers=(), package_format="native-v1"):
    import yaml

    config_paths = [
        *(f"responses_api_agents/{name}/configs/{name}.yaml" for name in agents),
        *(f"resources_servers/{name}/configs/{name}.yaml" for name in resources_servers),
    ]
    _write_manifest(env_dir, format=package_format, config_paths=config_paths)
    for name, relative_path in zip((*agents, *resources_servers), config_paths, strict=True):
        component_type = (
            "responses_api_agents" if relative_path.startswith("responses_api_agents/") else "resources_servers"
        )
        (env_dir / relative_path).write_text(
            yaml.safe_dump({name: {component_type: {f"{name}_implementation": {"entrypoint": "app.py"}}}}),
            encoding="utf-8",
        )
    if package_format == "wheels-v1":
        wheels_dir = env_dir / WHEELS_V1_SUBDIR
        wheels_dir.mkdir(exist_ok=True)
        (wheels_dir / "example_dependency-1.0-py3-none-any.whl").write_bytes(b"")
    return runtime._load_runtime_environment_package(str(env_dir), required=True)


def _component_selection(*, agent_config):
    return {
        runtime.ENVIRONMENT_COMPONENT_SELECTION_CONFIG_KEY: {
            "agent_instance": "selected_agent",
            "agent_config": agent_config,
            "resources_server_instance": "selected_resources",
            "resources_server_config": "resources_servers/selected_resources/configs/selected_resources.yaml",
            "model_config": "responses_api_models/inference_provider/configs/inference_provider.yaml",
        }
    }


@pytest.mark.parametrize(
    ("agents", "resources_servers", "agent_config", "expected_fallbacks"),
    [
        (("selected_agent",), ("selected_resources",), None, []),
        (
            ("selected_agent",),
            ("other_resources",),
            None,
            ["resources_servers/selected_resources/configs/selected_resources.yaml"],
        ),
        (
            ("other_agent",),
            ("selected_resources",),
            "responses_api_agents/selected_agent/configs/selected_agent.yaml",
            ["responses_api_agents/selected_agent/configs/selected_agent.yaml"],
        ),
        (
            ("other_agent",),
            ("other_resources",),
            "responses_api_agents/selected_agent/configs/selected_agent.yaml",
            [
                "responses_api_agents/selected_agent/configs/selected_agent.yaml",
                "resources_servers/selected_resources/configs/selected_resources.yaml",
            ],
        ),
    ],
    ids=["all-custom", "custom-agent", "custom-resources", "all-built-in"],
)
def test_environment_config_composes_custom_components_with_builtin_fallbacks(
    tmp_path,
    monkeypatch,
    agents,
    resources_servers,
    agent_config,
    expected_fallbacks,
):
    package = _load_composition_package(tmp_path, agents=agents, resources_servers=resources_servers)
    global_config = _component_selection(agent_config=agent_config)
    monkeypatch.setenv(runtime.NEMO_GYM_EXTRA_ROOTS_ENV_KEY, "/operator/root")

    runtime._configure_environment_package(global_config, package)

    package_paths = [str(path) for path in package.config_paths]
    model_config = "responses_api_models/inference_provider/configs/inference_provider.yaml"
    expected = [
        *package_paths,
        *(path for path in expected_fallbacks if path.startswith("responses_api_agents/")),
        model_config,
        *(path for path in expected_fallbacks if path.startswith("resources_servers/")),
    ]
    assert global_config["config_paths"] == expected
    assert runtime.ENVIRONMENT_COMPONENT_SELECTION_CONFIG_KEY not in global_config
    assert runtime.os.environ[runtime.NEMO_GYM_EXTRA_ROOTS_ENV_KEY] == f"{tmp_path.resolve()}:/operator/root"


def test_environment_config_requires_agent_fallback_when_selected_agent_is_absent(tmp_path):
    package = _load_composition_package(tmp_path, agents=("other_agent",), resources_servers=("selected_resources",))
    global_config = _component_selection(agent_config=None)

    with pytest.raises(RuntimeError, match="no built-in agent_config fallback"):
        runtime._configure_environment_package(global_config, package)


def test_no_manifest_is_a_no_op(tmp_path, monkeypatch):
    # Image-provided environments have no manifest and must retain the existing startup behavior.
    assert runtime._load_runtime_environment_package(str(tmp_path), required=False) is None


def test_no_environment_path_is_a_no_op(monkeypatch):
    # Curated Gym configurations can run without mounting a custom environment.
    assert runtime._load_runtime_environment_package("", required=False) is None


def test_explicit_environment_requires_a_manifest(tmp_path):
    with pytest.raises(RuntimeError, match="missing required manifest"):
        runtime._load_runtime_environment_package(str(tmp_path), required=True)


def test_native_v1_is_loaded_without_installing_wheels(tmp_path, monkeypatch):
    _write_manifest(tmp_path, format="native-v1")

    package = runtime._load_runtime_environment_package(str(tmp_path), required=True)

    assert package is not None
    assert package.manifest.format == "native-v1"

    def fail_install(*args, **kwargs):
        pytest.fail("native-v1 must not install wheels")

    monkeypatch.setattr(runtime.subprocess, "run", fail_install)
    runtime._install_wheels_v1_dependencies(package, str(tmp_path / "work"))


def test_wheels_v1_with_no_wheels_directory_raises(tmp_path):
    # Declaring wheels-v1 without its required wheelhouse indicates an incomplete bundle.
    _write_manifest(tmp_path, format="wheels-v1")

    with pytest.raises(RuntimeError, match="invalid Gym environment package"):
        runtime._load_runtime_environment_package(str(tmp_path), required=True)


def test_wheels_v1_with_an_empty_wheels_directory_raises(tmp_path):
    # An empty wheelhouse is invalid for the same reason as a missing one.
    _write_manifest(tmp_path, format="wheels-v1")
    (tmp_path / WHEELS_V1_SUBDIR).mkdir()

    with pytest.raises(RuntimeError, match="non-empty wheels/ directory"):
        runtime._load_runtime_environment_package(str(tmp_path), required=True)


def test_malformed_manifest_fails_before_gym_startup(tmp_path):
    (tmp_path / runtime.ENVIRONMENT_MANIFEST_FILENAME).write_text("format: [native-v1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="nemo-environment.yaml is not valid YAML"):
        runtime._load_runtime_environment_package(str(tmp_path), required=True)


def test_wheels_v1_installs_every_wheel_with_no_index_access(tmp_path, monkeypatch, isolated_gym_host_process_state):
    # Model the fixed bundle layout: manifest at the root and wheels in the sibling `wheels/`.
    _write_manifest(tmp_path, format="wheels-v1")
    wheels_dir = tmp_path / WHEELS_V1_SUBDIR
    work_dir = tmp_path / "work"
    wheels_dir.mkdir()
    (wheels_dir / "a_dep-1.0-py3-none-any.whl").write_bytes(b"")
    (wheels_dir / "b_dep-2.0-py3-none-any.whl").write_bytes(b"")

    # Capture the uv command without trying to install these intentionally empty wheel fixtures.
    calls = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setenv("PYTHONPATH", "/image/packages")

    package = runtime._load_runtime_environment_package(str(tmp_path), required=True)
    runtime._install_wheels_v1_dependencies(package, str(work_dir))

    assert len(calls) == 1
    (args,), kwargs = calls[0]
    install_dir = work_dir / runtime.WHEELS_V1_INSTALL_SUBDIR
    assert args[:10] == [
        "uv",
        "pip",
        "install",
        "--target",
        str(install_dir),
        "--no-index",
        "--only-binary",
        ":all:",
        "--find-links",
        str(wheels_dir),
    ]
    # Every .whl is installed explicitly.
    assert args[10:] == [
        str(wheels_dir / "a_dep-1.0-py3-none-any.whl"),
        str(wheels_dir / "b_dep-2.0-py3-none-any.whl"),
    ]
    assert kwargs == {"check": True}
    assert install_dir.is_dir()
    assert runtime.os.environ[runtime.UV_FIND_LINKS_ENV_KEY] == str(wheels_dir)
    # Child processes and the already-running host both prefer staged packages over image packages.
    assert runtime.os.environ["PYTHONPATH"] == f"{install_dir}{runtime.os.pathsep}/image/packages"
    assert runtime.sys.path[0] == str(install_dir)


def test_bootstrap_composes_a_wheels_package_like_native_v1(tmp_path, monkeypatch):
    # wheels-v1 and native-v1 are the same environment; only dependency install differs.
    package = _load_composition_package(
        tmp_path,
        agents=("selected_agent",),
        resources_servers=("selected_resources",),
        package_format="wheels-v1",
    )
    captured: dict[str, object] = {}

    class FakeRunHelper:
        def start(self, config):
            captured["config"] = config

    class FakeBaseServerConfig:
        def __init__(self, *, host, port):
            self.host = host
            self.port = port

    fake_modules = {
        "nemo_gym": ModuleType("nemo_gym"),
        "nemo_gym.cli": ModuleType("nemo_gym.cli"),
        "nemo_gym.cli.env": ModuleType("nemo_gym.cli.env"),
        "nemo_gym.global_config": ModuleType("nemo_gym.global_config"),
        "nemo_gym.server_utils": ModuleType("nemo_gym.server_utils"),
        "omegaconf": ModuleType("omegaconf"),
    }
    setattr(fake_modules["nemo_gym.cli.env"], "RunHelper", FakeRunHelper)
    setattr(fake_modules["nemo_gym.global_config"], "GlobalConfigDictParserConfig", lambda **kwargs: kwargs)
    setattr(fake_modules["nemo_gym.server_utils"], "BaseServerConfig", FakeBaseServerConfig)
    setattr(fake_modules["omegaconf"], "DictConfig", lambda value: value)
    for name, module in fake_modules.items():
        monkeypatch.setitem(runtime.sys.modules, name, module)

    caller_agent_config = "responses_api_agents/simple_agent/configs/simple_agent.yaml"
    model_config = "responses_api_models/inference_provider/configs/inference_provider.yaml"
    monkeypatch.setattr(
        runtime,
        "_load_global_config_dict",
        lambda: {
            "config_paths": [caller_agent_config],
            **_component_selection(agent_config=caller_agent_config),
        },
    )
    monkeypatch.setattr(runtime, "_apply_uv_dirs", lambda config: None)
    monkeypatch.setattr(runtime, "_allocate_head_server_port", lambda config: 5000)
    monkeypatch.setattr(runtime, "_create_rollout_helper", lambda: "rollout-helper")
    monkeypatch.setattr(runtime, "_install_wheels_v1_dependencies", lambda loaded_package, work_path: None)
    monkeypatch.setenv("NMP_ENVIRONMENT_PATH", str(tmp_path))
    monkeypatch.setenv(runtime.ENVIRONMENT_PACKAGE_REQUIRED_ENV_KEY, "true")
    monkeypatch.setenv("NMP_WORK_PATH", str(tmp_path / "work"))
    monkeypatch.setenv(runtime.NEMO_GYM_EXTRA_ROOTS_ENV_KEY, "/operator/root")

    runtime.bootstrap_gym_host()

    config = cast(dict[str, Any], captured["config"])
    composed = cast(dict[str, Any], config["initial_global_config_dict"])
    assert composed["config_paths"] == [
        *[str(path) for path in package.config_paths],
        model_config,
    ]
    assert caller_agent_config not in composed["config_paths"]
    assert runtime.ENVIRONMENT_COMPONENT_SELECTION_CONFIG_KEY not in composed
    assert runtime.os.environ[runtime.NEMO_GYM_EXTRA_ROOTS_ENV_KEY] == f"{tmp_path.resolve()}:/operator/root"


def test_bootstrap_installs_wheels_before_starting_gym(monkeypatch):
    # Record bootstrap milestones so the assertion verifies ordering rather than only invocation.
    events = []

    class FakeRunHelper:
        def start(self, config):
            events.append("gym-started")

    class FakeBaseServerConfig:
        def __init__(self, *, host, port):
            self.host = host
            self.port = port

    # NeMo-Gym is supplied by the runtime image rather than this test environment, so provide only
    # the small API surface bootstrap imports.
    fake_modules = {
        "nemo_gym": ModuleType("nemo_gym"),
        "nemo_gym.cli": ModuleType("nemo_gym.cli"),
        "nemo_gym.cli.env": ModuleType("nemo_gym.cli.env"),
        "nemo_gym.global_config": ModuleType("nemo_gym.global_config"),
        "nemo_gym.server_utils": ModuleType("nemo_gym.server_utils"),
        "omegaconf": ModuleType("omegaconf"),
    }
    setattr(fake_modules["nemo_gym.cli.env"], "RunHelper", FakeRunHelper)
    setattr(fake_modules["nemo_gym.global_config"], "GlobalConfigDictParserConfig", lambda **kwargs: kwargs)
    setattr(fake_modules["nemo_gym.server_utils"], "BaseServerConfig", FakeBaseServerConfig)
    setattr(fake_modules["omegaconf"], "DictConfig", lambda value: value)
    for name, module in fake_modules.items():
        monkeypatch.setitem(runtime.sys.modules, name, module)

    monkeypatch.setattr(runtime, "_load_global_config_dict", lambda: {})
    monkeypatch.setattr(runtime, "_apply_uv_dirs", lambda config: None)
    monkeypatch.setattr(runtime, "_allocate_head_server_port", lambda config: 5000)
    monkeypatch.setattr(runtime, "_create_rollout_helper", lambda: "rollout-helper")
    package = object()
    monkeypatch.setattr(
        runtime,
        "_load_runtime_environment_package",
        lambda environment_path, required: events.append("environment-validated") or package,
    )
    monkeypatch.setattr(
        runtime,
        "_configure_environment_package",
        lambda config, loaded_package: events.append("environment-composed") if loaded_package is package else None,
    )
    monkeypatch.setattr(
        runtime,
        "_install_wheels_v1_dependencies",
        lambda loaded_package, work_path: events.append("wheels-installed") if loaded_package is package else None,
    )
    monkeypatch.setenv("NMP_ENVIRONMENT_PATH", "/job/environment")
    monkeypatch.setenv(runtime.ENVIRONMENT_PACKAGE_REQUIRED_ENV_KEY, "true")
    monkeypatch.setenv("NMP_WORK_PATH", "/job/work")

    _, head_server_config, rollout_helper = runtime.bootstrap_gym_host()

    # Dependencies must be ready before RunHelper starts any Gym servers.
    assert events == ["environment-validated", "environment-composed", "wheels-installed", "gym-started"]
    assert head_server_config.host == "127.0.0.1"
    assert head_server_config.port == 5000
    assert rollout_helper == "rollout-helper"
