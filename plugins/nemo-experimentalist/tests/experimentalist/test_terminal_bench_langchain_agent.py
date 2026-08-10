# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import importlib.util
import io
import json
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "examples" / "terminal-bench-agent"


def _load_wrapper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("terminal_bench_harbor_wrapper", AGENT_DIR / "harbor_wrapper.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingEnvironment:
    def __init__(self, *, platform: str = "Linux\nx86_64\n") -> None:
        self.default_user = "root"
        self.platform = platform
        self.commands: list[dict[str, object]] = []
        self.uploads: dict[str, bytes] = {}

    async def exec(
        self,
        command: str,
        user: str | int | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> SimpleNamespace:
        self.commands.append(
            {
                "command": command,
                "user": user,
                "env": env,
                "cwd": cwd,
                "timeout_sec": timeout_sec,
            }
        )
        stdout = self.platform if command == "uname -s && uname -m" else ""
        return SimpleNamespace(return_code=0, stdout=stdout, stderr="")

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        self.uploads[target_path] = Path(source_path).read_bytes()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("amd64", "x86_64"), ("x86_64", "x86_64"), ("arm64", "aarch64"), ("aarch64", "aarch64")],
)
def test_static_uv_architecture_aliases(raw: str, expected: str) -> None:
    wrapper = _load_wrapper()

    assert wrapper._normalize_architecture(raw) == expected


def test_static_uv_architecture_rejects_unsupported_target() -> None:
    wrapper = _load_wrapper()

    with pytest.raises(RuntimeError, match="Unsupported.*riscv64"):
        wrapper._normalize_architecture("riscv64")


def test_uv_download_rejects_checksum_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wrapper = _load_wrapper()
    payload = b"not-the-pinned-uv-archive"
    monkeypatch.setattr(wrapper.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))
    destination = tmp_path / "uv.tar.gz"

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        wrapper._download_archive("https://example.invalid/uv.tar.gz", destination, "0" * 64)

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_uv_download_accepts_pinned_checksum(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wrapper = _load_wrapper()
    payload = b"pinned-uv-archive"
    monkeypatch.setattr(wrapper.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))
    destination = tmp_path / "uv.tar.gz"

    wrapper._download_archive(
        "https://example.invalid/uv.tar.gz",
        destination,
        hashlib.sha256(payload).hexdigest(),
    )

    assert destination.read_bytes() == payload


@pytest.mark.asyncio
async def test_installed_agent_stages_locked_uv_managed_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    wrapper = _load_wrapper()
    uv_binary = tmp_path / "uv"
    uv_binary.write_bytes(b"static uv")
    monkeypatch.setattr(wrapper, "_cached_uv_binary", lambda architecture: uv_binary)
    logs_dir = tmp_path / "logs"
    agent = wrapper.WrappedAgent(logs_dir=logs_dir, model_name="gateway/model")
    environment = RecordingEnvironment()

    await agent.install(environment)

    assert environment.uploads[wrapper.REMOTE_UV] == b"static uv"
    assert set(environment.uploads) == {
        wrapper.REMOTE_UV,
        *(f"{wrapper.REMOTE_PROJECT}/{name}" for name in wrapper.PROJECT_FILES),
    }
    commands = "\n".join(str(call["command"]) for call in environment.commands)
    assert f"{wrapper.REMOTE_UV} python install 3.12" in commands
    assert f"{wrapper.REMOTE_UV} sync --project {wrapper.REMOTE_PROJECT} --frozen --no-dev" in commands
    assert "curl" not in commands
    assert "apt" not in commands
    assert "docker" not in commands
    sync_call = next(call for call in environment.commands if " sync " in str(call["command"]))
    assert sync_call["env"]["UV_PYTHON_PREFERENCE"] == "only-managed"  # type: ignore[index]


@pytest.mark.asyncio
async def test_installed_agent_runs_module_in_app_and_populates_usage(tmp_path: Path) -> None:
    wrapper = _load_wrapper()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "summary.json").write_text(
        json.dumps(
            {
                "answer": "done",
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "cache_read_tokens": 3,
                },
            }
        ),
        encoding="utf-8",
    )
    agent = wrapper.WrappedAgent(
        logs_dir=logs_dir,
        model_name="aws/anthropic/claude-haiku-4-5-v1",
        extra_env={"INFERENCE_API_KEY": "test-key"},
    )
    environment = RecordingEnvironment()
    context = wrapper.AgentContext()

    await agent.run("solve it", environment, context)

    run_call = environment.commands[-1]
    command = str(run_call["command"])
    assert f"{wrapper.REMOTE_VENV}/bin/python -m main" in command
    assert run_call["cwd"] == "/app"
    assert run_call["env"]["INFERENCE_API_KEY"] == "test-key"  # type: ignore[index]
    assert "docker" not in command
    assert "sidecar" not in command
    assert context.n_input_tokens == 11
    assert context.n_output_tokens == 7
    assert context.n_cache_tokens == 3
    assert context.metadata is not None and context.metadata["answer"] == "done"


def test_agent_project_is_locked_and_has_no_nemo_oo_dependency() -> None:
    project = tomllib.loads((AGENT_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]

    assert (AGENT_DIR / "uv.lock").is_file()
    assert any(dependency.startswith("langchain") for dependency in dependencies)
    assert all("nemo-oo" not in dependency for dependency in dependencies)
