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

from pathlib import Path

from sandboxed_gym.host.entrypoint import (
    DEFAULT_GYM_ACTOR_VENV,
    DEFAULT_GYM_WRITABLE_SRC,
    DEFAULT_IMAGE_GIT_ROOT,
    default_gym_host_entrypoint,
    gym_host_script_path,
    packaged_gym_host_script,
)
from sandboxed_gym.runtime import gym_host_runtime as runtime


def test_default_gym_host_entrypoint_uses_sandboxed_actor_venv():
    entrypoint = default_gym_host_entrypoint()
    assert entrypoint[0] == "/bin/sh"
    assert entrypoint[1] == gym_host_script_path()
    assert entrypoint[2] == DEFAULT_GYM_ACTOR_VENV
    assert entrypoint[3] == DEFAULT_IMAGE_GIT_ROOT
    assert entrypoint[4] == DEFAULT_GYM_WRITABLE_SRC
    assert entrypoint[5].endswith("gym_host_runtime.py")
    script = packaged_gym_host_script()
    text = script.read_text(encoding="utf-8")
    assert "cp -a" in text
    assert "gym_host_runtime.py" in text


def test_apply_uv_dirs_fills_defaults(tmp_path, monkeypatch):
    cache = tmp_path / "uv-cache"
    venvs = tmp_path / "gym-venvs"
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.setenv("UV_CACHE_DIR", str(cache))
    monkeypatch.setenv("NEMO_GYM_VENV_DIR", str(venvs))
    cfg: dict = {}
    runtime._apply_uv_dirs(cfg)
    assert cfg["uv_cache_dir"] == str(cache)
    assert cfg["uv_venv_dir"] == str(venvs)


def test_apply_uv_dirs_preserves_config(tmp_path, monkeypatch):
    cache = tmp_path / "from-config-cache"
    venvs = tmp_path / "from-config-venvs"
    monkeypatch.setenv("NRL_CONTAINER", "1")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "ignored"))
    monkeypatch.setenv("NEMO_GYM_VENV_DIR", str(tmp_path / "ignored-venvs"))
    cfg = {"uv_cache_dir": str(cache), "uv_venv_dir": str(venvs)}
    runtime._apply_uv_dirs(cfg)
    assert cfg["uv_cache_dir"] == str(cache)
    assert cfg["uv_venv_dir"] == str(venvs)


def test_opensandbox_host_provider_defaults_skip_health_check():
    from sandboxed_gym.host.opensandbox import OpenSandboxGymHostProvider

    provider = OpenSandboxGymHostProvider(connection={"domain": "x", "api_key": "k"})
    assert provider._create_options["skip_health_check"] is True


def test_opensandbox_host_provider_honors_explicit_skip_health_check():
    from sandboxed_gym.host.opensandbox import OpenSandboxGymHostProvider

    provider = OpenSandboxGymHostProvider(
        connection={"domain": "x", "api_key": "k"},
        create={"skip_health_check": False},
    )
    assert provider._create_options["skip_health_check"] is False
