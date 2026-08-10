# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor installed-agent wrapper with an image-independent Python runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import tarfile
import urllib.request
import uuid
from pathlib import Path
from typing import override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

AGENT_DIR = Path(__file__).parent
PROJECT_FILES = ("agent.py", "main.py", "pyproject.toml", "tracing.py", "uv.lock")
REMOTE_ROOT = "/installed-agent"
REMOTE_PROJECT = f"{REMOTE_ROOT}/project"
REMOTE_UV = f"{REMOTE_ROOT}/bin/uv"
REMOTE_VENV = f"{REMOTE_ROOT}/venv"
REMOTE_PYTHON_INSTALLS = f"{REMOTE_ROOT}/python"
REMOTE_UV_CACHE = f"{REMOTE_ROOT}/uv-cache"
UV_VERSION = "0.9.5"
UV_ASSETS: dict[str, tuple[str, str]] = {
    "aarch64": (
        "uv-aarch64-unknown-linux-musl.tar.gz",
        "42b9b83933a289fe9c0e48f4973dee49ce0dfb95e19ea0b525ca0dbca3bce71f",
    ),
    "x86_64": (
        "uv-x86_64-unknown-linux-musl.tar.gz",
        "3665ffb6c429c31ad6c778ac0489b7746e691acf025cf530b3510b2f9b1660ff",
    ),
}


def _normalize_architecture(raw: str) -> str:
    aliases = {
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "x86_64": "x86_64",
    }
    normalized = aliases.get(raw.strip().lower())
    if normalized is None:
        supported = ", ".join(sorted(UV_ASSETS))
        raise RuntimeError(f"Unsupported task-container architecture {raw!r}; supported: {supported}")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as binary_file:
        for chunk in iter(lambda: binary_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_archive(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.partial")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "nemo-experimentalist/terminal-bench-agent"})
        with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as output:  # noqa: S310
            shutil.copyfileobj(response, output)
        actual_sha256 = _sha256(partial)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Downloaded uv archive checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)


def _cached_uv_binary(architecture: str) -> Path:
    asset_name, expected_sha256 = UV_ASSETS[architecture]
    default_cache = Path.cwd() / "tmp" / "runtime-cache"
    cache_root = Path(os.environ.get("NEMO_EXPERIMENTALIST_RUNTIME_CACHE", default_cache))
    release_dir = cache_root / f"uv-{UV_VERSION}"
    archive = release_dir / asset_name
    if not archive.is_file() or _sha256(archive) != expected_sha256:
        archive.unlink(missing_ok=True)
        url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{asset_name}"
        _download_archive(url, archive, expected_sha256)

    binary = release_dir / architecture / "uv"
    binary.parent.mkdir(parents=True, exist_ok=True)
    temporary_binary = binary.with_name(f"uv.{uuid.uuid4().hex}.partial")
    member_name = f"{asset_name.removesuffix('.tar.gz')}/uv"
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            member = bundle.getmember(member_name)
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError(f"Pinned uv archive does not contain {member_name}")
            with source, temporary_binary.open("wb") as output:
                shutil.copyfileobj(source, output)
        temporary_binary.chmod(0o755)
        os.replace(temporary_binary, binary)
    finally:
        temporary_binary.unlink(missing_ok=True)
    return binary


class WrappedAgent(BaseInstalledAgent):
    @staticmethod
    @override
    def name() -> str:
        return "nemo-experimentalist-langchain"

    @override
    def version(self) -> str | None:
        return "0.1.0"

    @staticmethod
    async def _target_architecture(environment: BaseEnvironment) -> str:
        result = await environment.exec("uname -s && uname -m")
        if result.return_code != 0:
            raise RuntimeError(f"Could not detect task-container platform: {result.stderr or result.stdout}")
        lines = (result.stdout or "").splitlines()
        if len(lines) != 2 or lines[0].strip() != "Linux":
            raise RuntimeError(f"Terminal-Bench installed agent requires a Linux task container, got {lines!r}")
        return _normalize_architecture(lines[1])

    @staticmethod
    def _runtime_env() -> dict[str, str]:
        return {
            "UV_CACHE_DIR": REMOTE_UV_CACHE,
            "UV_HTTP_TIMEOUT": "300",
            "UV_NO_PROGRESS": "1",
            "UV_PROJECT_ENVIRONMENT": REMOTE_VENV,
            "UV_PYTHON_INSTALL_DIR": REMOTE_PYTHON_INSTALLS,
            "UV_PYTHON_PREFERENCE": "only-managed",
        }

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        """Upload uv and create a locked uv-managed Python environment."""
        architecture = await self._target_architecture(environment)
        uv_binary = _cached_uv_binary(architecture)
        missing = [name for name in PROJECT_FILES if not (AGENT_DIR / name).is_file()]
        if missing:
            raise RuntimeError(f"Terminal-Bench agent project is incomplete; missing: {', '.join(missing)}")

        await self.exec_as_root(
            environment,
            command=(
                f"mkdir -p {REMOTE_ROOT}/bin {REMOTE_PROJECT} {REMOTE_VENV} "
                f"{REMOTE_PYTHON_INSTALLS} {REMOTE_UV_CACHE} && "
                f"chmod -R a+rwx {REMOTE_ROOT}"
            ),
        )
        await environment.upload_file(uv_binary, REMOTE_UV)
        for name in PROJECT_FILES:
            await environment.upload_file(AGENT_DIR / name, f"{REMOTE_PROJECT}/{name}")
        await self.exec_as_root(
            environment,
            command=f"chmod 0755 {REMOTE_UV} && chmod -R a+rX {REMOTE_PROJECT}",
        )
        await self.exec_as_agent(
            environment,
            command=(
                f"{REMOTE_UV} python install 3.12 && "
                f"{REMOTE_UV} sync --project {REMOTE_PROJECT} --frozen --no-dev && "
                f"{REMOTE_VENV}/bin/python -c "
                + shlex.quote("import langchain, langchain_openai; print('agent runtime OK')")
            ),
            env=self._runtime_env(),
            timeout_sec=600,
        )

    def _apply_summary(self, context: AgentContext) -> None:
        summary_path = self.logs_dir / "summary.json"
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(summary, dict):
            return
        answer = summary.get("answer")
        if isinstance(answer, str):
            context.metadata = {**(context.metadata or {}), "answer": answer}
        usage = summary.get("usage")
        if not isinstance(usage, dict):
            return
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        cache_read_tokens = usage.get("cache_read_tokens")
        if isinstance(input_tokens, int):
            context.n_input_tokens = input_tokens
        if isinstance(output_tokens, int):
            context.n_output_tokens = output_tokens
        if isinstance(cache_read_tokens, int):
            context.n_cache_tokens = cache_read_tokens

    @with_prompt_template
    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run the LangChain module directly in the canonical task container."""
        api_key = self._get_env("INFERENCE_API_KEY")
        if not api_key:
            raise RuntimeError("INFERENCE_API_KEY is required for the Terminal-Bench LangChain agent")

        prompt_path = self.logs_dir / "instruction.txt"
        prompt_path.write_text(instruction, encoding="utf-8")
        remote_prompt = f"{REMOTE_ROOT}/instruction.txt"
        await environment.upload_file(prompt_path, remote_prompt)

        env = {
            "INFERENCE_API_KEY": api_key,
            "INFERENCE_API_BASE": self._get_env("INFERENCE_API_BASE") or "https://inference-api.nvidia.com/v1",
            "PYTHONPATH": REMOTE_PROJECT,
        }
        model_name = self.model_name or self._get_env("AUT_MODEL_NAME")
        if model_name:
            env["EXPERIMENTALIST_MODEL"] = model_name

        command = (
            f"{REMOTE_VENV}/bin/python -m main "
            f"--prompt-file {shlex.quote(remote_prompt)} "
            "--trace-path /app/traces/trace.jsonl "
            "--summary-path /logs/agent/summary.json "
            "> /logs/agent/terminal-bench-agent.txt 2>&1; "
            "status=$?; "
            "cat /logs/agent/terminal-bench-agent.txt; "
            "mkdir -p /logs/artifacts/traces && "
            "cp -r /app/traces/. /logs/artifacts/traces/ 2>/dev/null || true; "
            "exit $status"
        )
        try:
            result = await self.exec_as_agent(
                environment,
                command=command,
                env=env,
                cwd="/app",
            )
            context.metadata = {
                **(context.metadata or {}),
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.return_code,
            }
        finally:
            self._apply_summary(context)
