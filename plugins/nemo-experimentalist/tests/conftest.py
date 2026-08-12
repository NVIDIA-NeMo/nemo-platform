# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist test-wide state isolation."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import cast

import litellm
import pytest
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients, ConfiguredModelRefs, activate_model_clients
from nooa.unifiedllm import CompletionClient, FakeLLMClient

# Some NVIDIA inference endpoint models reject the tool_choice parameter.
# Drop unsupported params silently so the CodeAct strategy can call tools.
litellm.drop_params = True

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "nemo-experimentalist"
_CI_ENV = "CI"
_SANDBOX_NAME_ENV = "SANDBOX_VM_ID"
_ALLOW_UNSANDBOXED_ENV = "SMOKE_AGENT_E2E_ALLOW_UNSANDBOXED"


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Check that marked E2E tests are isolated."""
    if "e2e" not in item.keywords:
        return
    if os.environ.get(_CI_ENV):
        pytest.skip("smoke-agent E2E tests are developer-invoked and do not run in CI")
    if os.environ.get(_SANDBOX_NAME_ENV) or os.environ.get(_ALLOW_UNSANDBOXED_ENV) == "1":
        return
    pytest.skip(
        "e2e executes model-written shell; set SANDBOX_VM_ID to an existing sbx sandbox "
        "or set SMOKE_AGENT_E2E_ALLOW_UNSANDBOXED=1"
    )


class SandboxRunner:
    """Run and fetch smoke-agent work."""

    def __init__(self, sandbox: str | None) -> None:
        self.sandbox = sandbox
        self.repo_root = _REPO_ROOT
        self.plugin_root = _PLUGIN_ROOT
        self.run_root = f"/tmp/nemo-experimentalist-smoke-e2e/{uuid.uuid4().hex}"
        self.remote_plugin_root = f"{self.run_root}/nemo-experimentalist"

    @property
    def platform_url(self) -> str:
        """Return the loop's Platform URL."""
        return "http://host.docker.internal:8080" if self.sandbox else "http://localhost:8080"

    def _sandbox_command(self, command: list[str], environment: dict[str, str] | None) -> list[str]:
        """Wrap one command for sbx."""
        if not self.sandbox:
            return command
        wrapped = ["sbx", "exec"]
        settings = {
            "UV_PROJECT_ENVIRONMENT": "/home/agent/.venvs/nemo-platform",
            "PYTHONPATH": f"{self.remote_plugin_root}/src",
            "OTLP_ENDPOINT": "http://host.docker.internal:5001/v1/traces",
            **(environment or {}),
        }
        for name, value in settings.items():
            wrapped.extend(["--env", f"{name}={value}"])
        return [*wrapped, "--workdir", str(self.repo_root), self.sandbox, *command]

    def run(
        self,
        command: list[str],
        *,
        log: Path,
        environment: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> str:
        """Run a command and write its output to the host log."""
        actual = self._sandbox_command(command, environment)
        process_environment = None if self.sandbox else environment
        with log.open("a", encoding="utf-8") as output:
            output.write("$ " + " ".join(shlex.quote(part) for part in actual) + "\n")
            output.flush()
            result = subprocess.run(
                actual,
                cwd=self.repo_root,
                env=process_environment,
                stdout=subprocess.PIPE if capture_output else output,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            if capture_output:
                output.write(result.stdout or "")
        if result.returncode:
            pytest.fail(f"E2E command failed; log: {log}\n{log.read_text(encoding='utf-8')}")
        return result.stdout or ""

    def bootstrap(self, *, log: Path) -> None:
        """Prepare the sandbox once for E2E loops."""
        if not self.sandbox:
            return
        self._create_sandbox_if_needed(log=log)
        check = subprocess.run(
            ["sbx", "exec", self.sandbox, "sh", "-lc", "command -v gcc && dpkg -s python3-dev >/dev/null"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write(f"$ sbx exec {self.sandbox} sh -lc 'command -v gcc && dpkg -s python3-dev >/dev/null'\n")
            output.write(check.stdout or "")
            output.write(check.stderr or "")
        if check.returncode:
            self._bootstrap_packages(log=log)
        self.run(
            [
                "uv",
                "sync",
                "--frozen",
                "--package",
                "nemo-experimentalist-plugin",
                "--package",
                "nemo-platform-plugin",
                "--package",
                "nemo-agents-plugin",
            ],
            log=log,
        )

    def _create_sandbox_if_needed(self, *, log: Path) -> None:
        """Create the configured sandbox when it is absent."""
        assert self.sandbox
        exists = subprocess.run(
            ["sbx", "ls", "--quiet"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write("$ sbx ls --quiet\n")
            output.write(exists.stdout or "")
            output.write(exists.stderr or "")
        if exists.returncode:
            pytest.fail(f"could not list sandboxes; log: {log}\n{log.read_text(encoding='utf-8')}")
        if self.sandbox in exists.stdout.splitlines():
            return
        command = [
            "sbx",
            "create",
            "--clone",
            "--name",
            self.sandbox,
            "shell",
            str(self.repo_root),
        ]
        result = subprocess.run(command, cwd=self.repo_root, capture_output=True, text=True, check=False)
        with log.open("a", encoding="utf-8") as output:
            output.write("$ " + " ".join(shlex.quote(part) for part in command) + "\n")
            output.write(result.stdout or "")
            output.write(result.stderr or "")
        if result.returncode:
            pytest.fail(f"could not create sandbox {self.sandbox!r}; log: {log}\n{log.read_text(encoding='utf-8')}")

    def _bootstrap_packages(self, *, log: Path) -> None:
        """Install native build prerequisites."""
        assert self.sandbox
        command = [
            "sbx",
            "exec",
            "--user",
            "root",
            self.sandbox,
            "sh",
            "-lc",
            "apt-get update && apt-get install -y --no-install-recommends build-essential python3-dev",
        ]
        result = subprocess.run(command, cwd=self.repo_root, capture_output=True, text=True, check=False)
        with log.open("a", encoding="utf-8") as output:
            output.write("$ " + " ".join(shlex.quote(part) for part in command) + "\n")
            output.write(result.stdout or "")
            output.write(result.stderr or "")
        if result.returncode:
            pytest.fail(f"could not install sandbox build prerequisites; log: {log}\n{log.read_text(encoding='utf-8')}")

    def sync(self, *, log: Path) -> None:
        """Copy the plugin tree into the sandbox."""
        if not self.sandbox:
            return
        self.run(["mkdir", "-p", self.run_root], log=log)
        result = subprocess.run(
            ["sbx", "cp", str(self.plugin_root), f"{self.sandbox}:{self.run_root}"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write(f"$ sbx cp {self.plugin_root} {self.sandbox}:{self.run_root}\n")
            output.write(result.stdout or "")
            output.write(result.stderr or "")
        if result.returncode:
            pytest.fail(f"could not sync the Experimentalist worktree; log: {log}\n{log.read_text(encoding='utf-8')}")
        ownership = subprocess.run(
            ["sbx", "exec", "--user", "root", self.sandbox, "chown", "-R", "agent:agent", self.remote_plugin_root],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write(f"$ sbx exec --user root {self.sandbox} chown -R agent:agent {self.remote_plugin_root}\n")
            output.write(ownership.stdout or "")
            output.write(ownership.stderr or "")
        if ownership.returncode:
            pytest.fail(f"could not prepare the synced plugin tree; log: {log}\n{log.read_text(encoding='utf-8')}")

    def prepare_fixture(self, artifact_parent: Path, *, log: Path) -> tuple[str, str]:
        """Create one isolated fixture copy."""
        if not self.sandbox:
            fixture = artifact_parent / "workspace" / "smoke-agent"
            fixture.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.plugin_root / "examples" / "smoke-agent", fixture)
            return str(fixture), str(artifact_parent / "experiment")
        remote_parent = f"{self.run_root}/{artifact_parent.name}-{uuid.uuid4().hex}"
        remote_fixture = f"{remote_parent}/workspace/smoke-agent"
        self.run(
            [
                "sh",
                "-lc",
                f"mkdir -p {shlex.quote(remote_parent + '/workspace')} && cp -a "
                f"{shlex.quote(self.remote_plugin_root + '/examples/smoke-agent')} {shlex.quote(remote_fixture)}",
            ],
            log=log,
        )
        return remote_fixture, f"{remote_parent}/experiment"

    def source_path(self, path: Path) -> str:
        """Return a source path visible to the loop."""
        if not self.sandbox:
            return str(path)
        return str(Path(self.remote_plugin_root) / path.relative_to(self.plugin_root))

    def replace_text(self, path: str, old: str, new: str, *, log: Path) -> None:
        """Edit a fixture file owned by this test."""
        if not self.sandbox:
            local = Path(path)
            local.write_text(local.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
            return
        script = "import pathlib, sys; path=pathlib.Path(sys.argv[1]); path.write_text(path.read_text().replace(sys.argv[2], sys.argv[3]))"
        self.run(["python3", "-c", script, path, old, new], log=log)

    def make_directories(self, *paths: str, log: Path) -> None:
        """Create fixture directories."""
        if self.sandbox:
            self.run(["mkdir", "-p", *paths], log=log)
        else:
            for path in paths:
                Path(path).mkdir(parents=True, exist_ok=True)

    def copy_in(self, source: Path, destination: str, *, log: Path) -> None:
        """Copy a host file into the sandbox."""
        if not self.sandbox:
            return
        result = subprocess.run(
            ["sbx", "cp", str(source), f"{self.sandbox}:{destination}"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write(f"$ sbx cp {source} {self.sandbox}:{destination}\n")
            output.write(result.stdout or "")
            output.write(result.stderr or "")
        if result.returncode:
            pytest.fail(f"could not copy E2E input into sandbox; log: {log}\n{log.read_text(encoding='utf-8')}")

    def fetch(self, remote_path: str, local_parent: Path, *, log: Path) -> None:
        """Download a sandbox artifact into pytest's directory."""
        if not self.sandbox:
            return
        local_parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["sbx", "cp", f"{self.sandbox}:{remote_path}", str(local_parent)],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        with log.open("a", encoding="utf-8") as output:
            output.write(f"$ sbx cp {self.sandbox}:{remote_path} {local_parent}\n")
            output.write(result.stdout or "")
            output.write(result.stderr or "")
        if result.returncode:
            pytest.fail(f"could not fetch sandbox E2E artifacts; log: {log}\n{log.read_text(encoding='utf-8')}")


@pytest.fixture(scope="session")
def sandbox_runner() -> SandboxRunner:
    """Provide one shared sandbox runner."""
    sandbox = os.environ.get(_SANDBOX_NAME_ENV)
    runtime = SandboxRunner(sandbox)
    log = Path("/tmp") / f"smoke-agent-e2e-sync-{uuid.uuid4().hex}.log"
    runtime.bootstrap(log=log)
    runtime.sync(log=log)
    return runtime


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes and activate hermetic agent models.

    The CLI loads a profile's .env straight into os.environ. When the variable was
    previously unset, monkeypatch has nothing recorded to restore, so the value
    survives the test and leaks into whatever else the xdist worker runs next.

    """
    snapshot = os.environ.copy()
    os.environ["NEMO_DEFAULT_MODEL"] = "default/fake"
    os.environ["NEMO_FAST_MODEL"] = "default/fake"
    fake = FakeLLMClient()
    clients = ConfiguredModelClients(
        default=cast(CompletionClient, fake),
        fast=cast(CompletionClient, fake),
        refs=ConfiguredModelRefs(default="default/fake", fast="default/fake"),
    )
    with activate_model_clients(clients):
        yield
    os.environ.clear()
    os.environ.update(snapshot)
