# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Preflight checks. Each ``*_ok`` returns ``(ok, detail)``; :func:`run_checks` labels them."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import NamedTuple

import typer
from nemo_iron_swarm_plugin.config import INFERENCE_API_KEY_ENVVAR, IronSwarmConfig, read_env_file

# The OpenShell gateway iron-swarm's `scripts/setup.sh` registers for the defender control plane.
OPENSHELL_GATEWAY = "auto-defender"

# Every mutating command gates on these probes, so the timeout is a ceiling for a *wedged* daemon,
# not a budget for a healthy one — both answer in well under a second when up.
PROBE_TIMEOUT_SECONDS = 5

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# `openshell status` prints an aligned "  Status: Connected" row (color-coded, no JSON mode).
_STATUS_ROW = re.compile(r"^\s*Status:\s*(?P<value>.+?)\s*$", re.MULTILINE)


class CheckResult(NamedTuple):
    """One preflight row. A NamedTuple so callers can unpack it or use named fields."""

    label: str
    ok: bool
    detail: str


def docker_ok() -> tuple[bool, str]:
    """True if the Docker CLI is present and the daemon is reachable."""
    if shutil.which("docker") is None:
        return False, "docker CLI not found — install Docker: https://docs.docker.com/engine/install/"
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return False, f"`docker info` timed out after {PROBE_TIMEOUT_SECONDS}s — the daemon looks wedged."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run `docker info`: {exc}"
    if proc.returncode != 0:
        return False, "Docker daemon not reachable — start Docker, then retry."
    return True, "Docker daemon reachable."


def openshell_gateway_ok() -> tuple[bool, str]:
    """True if the OpenShell CLI reports the auto-defender gateway as Connected."""
    if shutil.which("openshell") is None:
        return False, (
            "openshell CLI not found — install it: "
            "curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh"
        )
    try:
        proc = subprocess.run(
            ["openshell", "status", "--gateway", OPENSHELL_GATEWAY],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"`openshell status` timed out after {PROBE_TIMEOUT_SECONDS}s — the gateway is unresponsive."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run `openshell status`: {exc}"
    status = gateway_status(proc.stdout)
    if proc.returncode == 0 and status.casefold() == "connected":
        return True, f"OpenShell gateway '{OPENSHELL_GATEWAY}' connected."
    reported = f" (reported: {status})" if status else ""
    return False, f"OpenShell gateway '{OPENSHELL_GATEWAY}' not connected{reported} — run `nemo iron-swarm setup`."


def gateway_status(stdout: str) -> str:
    """The value of ``openshell status``'s ``Status:`` row, ANSI stripped; ``""`` if absent.

    Matching the whole field rather than substring-searching for "Connected" — otherwise
    ``Not Connected`` and ``Last Connected: ...`` both read as healthy.
    """
    match = _STATUS_ROW.search(_ANSI.sub("", stdout))
    return match.group("value").strip() if match else ""


def venv_ok(config: IronSwarmConfig) -> tuple[bool, str]:
    """True if iron-swarm's dedicated venv has been provisioned."""
    if config.iron_swarm_bin.exists():
        return True, f"iron-swarm venv present at {config.venv_path}."
    return False, (f"iron-swarm venv missing at {config.venv_path} — run `nemo iron-swarm setup`.")


def garak_venv_ok(config: IronSwarmConfig) -> tuple[bool, str]:
    """True if the dedicated garak venv (used by iron-swarm's agent_breaker) is provisioned."""
    if config.garak_python.exists():
        return True, f"garak venv present at {config.garak_venv_path}."
    return False, (f"garak venv missing at {config.garak_venv_path} — run `nemo iron-swarm setup`.")


def operator_env_ok(config: IronSwarmConfig) -> tuple[bool, str]:
    """True if iron-swarm's own inference credential is resolvable (env or operator dotenv)."""
    if os.environ.get(INFERENCE_API_KEY_ENVVAR):
        return True, f"{INFERENCE_API_KEY_ENVVAR} set in the environment."
    if read_env_file(config.operator_env_file).get(INFERENCE_API_KEY_ENVVAR):
        return True, f"{INFERENCE_API_KEY_ENVVAR} present in {config.operator_env_file}."
    return False, (
        f"{INFERENCE_API_KEY_ENVVAR} not found — run `nemo iron-swarm setup` (or export {INFERENCE_API_KEY_ENVVAR})."
    )


def run_checks(config: IronSwarmConfig) -> list[CheckResult]:
    """Run all preflight checks."""
    return [
        CheckResult("iron-swarm venv", *venv_ok(config)),
        CheckResult("garak venv", *garak_venv_ok(config)),
        CheckResult("inference credential", *operator_env_ok(config)),
        CheckResult("docker", *docker_ok()),
        CheckResult("openshell gateway", *openshell_gateway_ok()),
    ]


def print_checks(checks: list[CheckResult]) -> None:
    for check in checks:
        mark = typer.style("✓", fg="green") if check.ok else typer.style("✗", fg="red")
        typer.echo(f"  {mark} {check.label}: {check.detail}")


def require_preflight(config: IronSwarmConfig) -> None:
    """Gate init/run on preflight when sandbox is required."""
    if not config.require_sandbox:
        return
    checks = run_checks(config)
    if not all(check.ok for check in checks):
        typer.secho("Preflight failed:", fg="red")
        print_checks(checks)
        typer.secho("\nRun `nemo iron-swarm setup` first.", fg="yellow")
        raise typer.Exit(code=1)
