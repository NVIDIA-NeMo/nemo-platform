# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx


def _compose_lifecycle(env: dict[str, str] | None) -> str:
    lifecycle = (env or {}).get("AUTHENTIK_E2E_LIFECYCLE", os.environ.get("AUTHENTIK_E2E_LIFECYCLE", "fresh"))
    if lifecycle not in {"fresh", "reuse"}:
        raise ValueError(f"unsupported AUTHENTIK_E2E_LIFECYCLE: {lifecycle}")
    return lifecycle


def _compose_env(env: dict[str, str] | None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return merged


def _compose_base_args(compose_file: Path, project_name: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), "-p", project_name]


class DockerComposeE2EBackend:
    def __init__(
        self,
        *,
        compose_file: Path,
        config_path: Path,
        project_name: str,
        service_url: str,
        wait_url: str | None = None,
        env: dict[str, str] | None = None,
        wait_timeout_seconds: int = 180,
    ) -> None:
        self.compose_file = compose_file
        self.config_path = config_path
        self.project_name = project_name
        self.service_url = service_url
        self.wait_url = wait_url or service_url
        self.env = {
            "NEMO_COMPOSE_CONFIG_PATH": str(config_path.resolve()),
            **(env or {}),
        }
        self.lifecycle = _compose_lifecycle(self.env)
        self.wait_timeout_seconds = wait_timeout_seconds

    def _run(self, *extra_args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
        args = _compose_base_args(self.compose_file, self.project_name)
        args.extend(extra_args)
        return subprocess.run(
            args,
            check=True,
            text=True,
            capture_output=capture_output,
            env=_compose_env(self.env),
        )

    def _services(self, *extra_args: str) -> set[str]:
        result = self._run(*extra_args, capture_output=True)
        return {line for line in result.stdout.splitlines() if line}

    def start(self) -> None:
        expected_services = self._services("config", "--services")
        if self.lifecycle == "reuse":
            running_services = self._services("ps", "--services", "--status", "running")
            if running_services == expected_services:
                self._wait_ready()
                return
        else:
            try:
                self.stop()
            except subprocess.CalledProcessError:
                pass

        self._run("up", "-d")

        deadline = time.monotonic() + self.wait_timeout_seconds
        while time.monotonic() < deadline:
            running_services = self._services("ps", "--services", "--status", "running")
            if running_services == expected_services:
                break
            self._run("up", "-d")
            time.sleep(2)
        else:
            missing = sorted(expected_services - self._services("ps", "--services", "--status", "running"))
            raise TimeoutError(f"compose services did not all reach running state for {self.project_name}: {missing}")

        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.wait_timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = httpx.get(self.wait_url, timeout=5)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2)
        raise TimeoutError(f"compose backend did not become ready: {self.wait_url}")

    def stop(self) -> None:
        if self.lifecycle == "reuse":
            return
        self._run("down", "-v")
