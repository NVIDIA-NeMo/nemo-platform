# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
import time
from os import environ
from pathlib import Path
from typing import TypeAlias

import httpx

from tests.auth_idp.providers import ProviderConfig

ComposeFiles: TypeAlias = Path | tuple[Path, ...]
ComposeEnv: TypeAlias = dict[str, str] | None


def _compose_lifecycle(env: ComposeEnv) -> str:
    lifecycle = (env or {}).get("AUTHENTIK_E2E_LIFECYCLE", environ.get("AUTHENTIK_E2E_LIFECYCLE", "fresh"))
    if lifecycle not in {"fresh", "reuse"}:
        raise ValueError(f"unsupported AUTHENTIK_E2E_LIFECYCLE: {lifecycle}")
    return lifecycle


def _compose_base_args(compose_file: ComposeFiles, project_name: str | None) -> list[str]:
    args = ["docker", "compose"]
    compose_files = (compose_file,) if isinstance(compose_file, Path) else compose_file
    for path in compose_files:
        args.extend(["-f", str(path)])
    if project_name:
        args.extend(["-p", project_name])
    return args


def _compose_env(env: ComposeEnv) -> dict[str, str]:
    merged = dict(environ)
    if env:
        merged.update(env)
    return merged


def _compose_services(
    compose_file: ComposeFiles,
    project_name: str | None,
    *extra_args: str,
    env: ComposeEnv = None,
) -> set[str]:
    args = _compose_base_args(compose_file, project_name)
    args.extend(extra_args)
    result = subprocess.run(args, check=True, capture_output=True, text=True, env=_compose_env(env))
    return {line for line in result.stdout.splitlines() if line}


def _compose_diagnostics_prefix(compose_file: ComposeFiles, project_name: str | None) -> str:
    primary = compose_file[0] if isinstance(compose_file, tuple) else compose_file
    raw = project_name or primary.parent.name or primary.stem
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in raw)


def collect_compose_diagnostics(
    compose_file: ComposeFiles,
    *,
    project_name: str | None = None,
    env: ComposeEnv = None,
) -> Path | None:
    log_dir = environ.get("E2E_SERVICES_LOG_DIR")
    if not log_dir:
        return None

    output_dir = Path(log_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = _compose_diagnostics_prefix(compose_file, project_name)
    commands = {
        "ps": ["ps", "--all"],
        "logs": ["logs", "--no-color"],
    }
    for suffix, extra_args in commands.items():
        args = _compose_base_args(compose_file, project_name)
        args.extend(extra_args)
        output_path = output_dir / f"{prefix}.{suffix}.txt"
        try:
            result = subprocess.run(args, check=True, capture_output=True, text=True, env=_compose_env(env))
            contents = result.stdout
            if result.stderr:
                contents = f"{contents}\n[stderr]\n{result.stderr}" if contents else f"[stderr]\n{result.stderr}"
        except Exception as exc:
            contents = f"Failed to collect compose diagnostics for {suffix}: {exc}\n"
        output_path.write_text(contents)
    return output_dir


def compose_up(
    compose_file: ComposeFiles,
    *,
    project_name: str | None = None,
    wait_timeout: int | None = None,
    env: ComposeEnv = None,
) -> None:
    lifecycle = _compose_lifecycle(env)
    args = _compose_base_args(compose_file, project_name)
    args.extend(["up", "-d"])

    expected_services = _compose_services(compose_file, project_name, "config", "--services", env=env)
    if lifecycle == "reuse":
        running_services = _compose_services(
            compose_file,
            project_name,
            "ps",
            "--services",
            "--status",
            "running",
            env=env,
        )
        if running_services == expected_services:
            return

    subprocess.run(args, check=True, env=_compose_env(env))

    if wait_timeout is None:
        return

    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        running_services = _compose_services(
            compose_file,
            project_name,
            "ps",
            "--services",
            "--status",
            "running",
            env=env,
        )
        if running_services == expected_services:
            return

        # Some services stay in "Created" until their healthy dependencies settle.
        # Re-issuing `up -d` lets Compose advance them once those deps are ready.
        subprocess.run(args, check=True, env=_compose_env(env))
        time.sleep(2)

    project = f" for compose project {project_name}" if project_name else ""
    missing = sorted(
        expected_services
        - _compose_services(compose_file, project_name, "ps", "--services", "--status", "running", env=env)
    )
    raise TimeoutError(f"compose services did not all reach running state{project}: {missing}")


def compose_down(compose_file: ComposeFiles, *, project_name: str | None = None, env: ComposeEnv = None) -> None:
    if _compose_lifecycle(env) == "reuse":
        return
    args = _compose_base_args(compose_file, project_name)
    args.extend(["down", "-v"])
    subprocess.run(args, check=True, env=_compose_env(env))


def compose_published_port(
    compose_file: ComposeFiles,
    service: str,
    container_port: int,
    *,
    project_name: str | None = None,
    env: ComposeEnv = None,
) -> int:
    args = _compose_base_args(compose_file, project_name)
    args.extend(["port", service, str(container_port)])
    result = subprocess.run(args, check=True, capture_output=True, text=True, env=_compose_env(env))
    for line in result.stdout.splitlines():
        address = line.strip()
        if address:
            return int(address.rsplit(":", 1)[1])
    raise RuntimeError(f"compose did not publish a host port for {service}:{container_port}")


def wait_for_healthchecks(provider: ProviderConfig, timeout: float = 120) -> None:
    for check in provider.healthchecks:
        if check.get("kind") != "http":
            continue
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = httpx.get(check["url"], timeout=5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise TimeoutError(f"healthcheck did not pass: {check['url']}")


def wait_for_gateway_listener(base_url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(base_url, timeout=5)
            if response.status_code >= 100:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError(f"gateway did not become reachable: {base_url}")


def wait_for_token_endpoint(provider: ProviderConfig, timeout: float = 60) -> str:
    if provider.token_endpoint is None or provider.machine_grant is None:
        raise ValueError(f"provider {provider.name} does not declare machine token acquisition")

    deadline = time.monotonic() + timeout
    last_error: httpx.RequestError | None = None
    last_response: httpx.Response | None = None
    while time.monotonic() < deadline:
        try:
            grant = provider.machine_grant
            data = {
                "grant_type": grant["grant_type"],
                "client_id": grant["client_id"],
            }
            if "client_secret" in grant:
                data["client_secret"] = grant["client_secret"]
            if grant["grant_type"] == "password":
                data["username"] = grant["username"]
                data["password"] = grant["password"]
            if "scope" in grant:
                data["scope"] = grant["scope"]
            response = httpx.post(
                provider.token_endpoint,
                data=data,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            last_error = exc
            time.sleep(2)
            continue
        last_response = response
        if response.status_code < 500:
            response.raise_for_status()
            return response.json()["access_token"]
        time.sleep(2)
    if last_response is not None:
        last_response.raise_for_status()
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"token endpoint did not become reachable: {provider.token_endpoint}")
