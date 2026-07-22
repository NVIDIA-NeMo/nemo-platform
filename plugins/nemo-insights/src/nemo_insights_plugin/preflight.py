# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only readiness checks for Insights analysis."""

import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from nemo_insights_plugin.analyst.analyst_backend import make_analyst_backend
from nemo_insights_plugin.client import make_client
from nemo_insights_plugin.contracts.checks import CheckResult, make_check_result
from nemo_insights_plugin.profile import AnalysisProfile
from nemo_platform import AsyncNeMoPlatform, NeMoPlatformError

_EXPECTED_PLATFORM_ERRORS = (NeMoPlatformError, httpx.HTTPError, OSError, RuntimeError, ValueError)


def _default_http_ok(base_url: str) -> bool:
    try:
        return (
            httpx.get(
                f"{base_url.rstrip('/')}/health/ready",
                timeout=5,
                follow_redirects=True,
            ).status_code
            < 500
        )
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return False


async def _default_workspace_ok(base_url: str, workspace: str, agent: str) -> bool:
    client: AsyncNeMoPlatform | None = None
    try:
        client = make_client(base_url)
        backend = make_analyst_backend(client=client, insights_output=None)
        await backend.count_agent_sessions(agent=agent, workspace=workspace)
        return True
    except _EXPECTED_PLATFORM_ERRORS:
        return False
    finally:
        if client is not None:
            try:
                await client.close()
            except _EXPECTED_PLATFORM_ERRORS:
                pass


@dataclass(frozen=True)
class AnalysisProbes:
    """Dependencies used by read-only environment checks."""

    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    http_ok: Callable[[str], bool] = _default_http_ok
    workspace_ok: Callable[[str, str, str], Awaitable[bool]] = _default_workspace_ok


def check_profile(
    profile: AnalysisProfile | None,
    profile_error: str | None,
) -> list[CheckResult]:
    """Check that a profile was found and parsed."""
    if profile_error is not None:
        return [
            CheckResult(
                name="profile-parse",
                group="profile",
                status="fail",
                severity="required",
                message=profile_error,
                hint="fix optimizer.yaml or pass --profile with a valid file",
            )
        ]
    if profile is None:
        return [
            CheckResult(
                name="profile-found",
                group="profile",
                status="fail",
                severity="required",
                message="no optimizer.yaml found (searched cwd and parents)",
                hint="create optimizer.yaml with at least `agent: <name>`",
            )
        ]
    return [
        CheckResult(
            name="profile-found",
            group="profile",
            status="pass",
            severity="required",
            message=f"profile for agent {profile.agent!r} at {profile.profile_dir}",
        )
    ]


def check_agent_spec(
    spec_path: Path | None,
    spec_error: str | None,
) -> list[CheckResult]:
    """Check the optional agent-spec artifact, including explicit UTF-8 readability."""
    return read_agent_spec(spec_path, spec_error)[1]


def read_agent_spec(
    spec_path: Path | None,
    spec_error: str | None,
) -> tuple[str | None, list[CheckResult]]:
    """Read the optional agent spec as UTF-8 and return its readiness check."""
    if spec_error is not None:
        return None, [
            CheckResult(
                name="agent-spec",
                group="artifacts",
                status="fail",
                severity="required",
                message=spec_error,
            )
        ]
    if spec_path is None:
        return None, [
            CheckResult(
                name="agent-spec",
                group="artifacts",
                status="pass",
                severity="advisory",
                message="agent spec omitted (optional)",
            )
        ]
    try:
        content = spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [
            CheckResult(
                name="agent-spec",
                group="artifacts",
                status="fail",
                severity="required",
                message=f"Could not read agent spec {spec_path} as UTF-8: {exc}",
                hint="ensure the file is readable and encoded as UTF-8",
            )
        ]
    return content, [
        CheckResult(
            name="agent-spec",
            group="artifacts",
            status="pass",
            severity="required",
            message=f"agent spec readable at {spec_path}",
        )
    ]


def check_credentials(
    profile_dir: Path | None,
    probes: AnalysisProbes | None = None,
) -> list[CheckResult]:
    """Check that the analyst's required inference credential is present."""
    active = probes or AnalysisProbes()
    env_path = profile_dir / ".env" if profile_dir is not None else None
    credential_hint = (
        f"save it in {env_path} or export INFERENCE_API_KEY=<key>"
        if env_path is not None
        else "export INFERENCE_API_KEY=<key>"
    )
    credential = bool(active.env.get("INFERENCE_API_KEY", "").strip())
    return [
        make_check_result(
            "INFERENCE_API_KEY",
            "credentials",
            credential,
            "required",
            "INFERENCE_API_KEY set",
            "INFERENCE_API_KEY not set",
            hint=credential_hint,
        )
    ]


async def check_environment(
    *,
    agent: str | None,
    workspace: str | None,
    base_url: str,
    profile_dir: Path | None,
    probes: AnalysisProbes | None = None,
) -> list[CheckResult]:
    """Run credential and advisory platform checks without persisting state.

    The workspace probe is profile-dependent and skipped when *agent* or
    *workspace* is unknown; the credential and reachability checks always run.
    """
    active = probes or AnalysisProbes()
    results = check_credentials(profile_dir, active)
    reachable = active.http_ok(base_url)
    results.append(
        make_check_result(
            "platform-reachable",
            "platform",
            reachable,
            "advisory",
            f"{base_url} reachable",
            f"{base_url} unreachable",
            hint="check --base-url/NMP_BASE_URL and platform health",
        )
    )
    if agent is not None and workspace is not None:
        queryable = await active.workspace_ok(base_url, workspace, agent)
        results.append(
            make_check_result(
                "workspace-query",
                "platform",
                queryable,
                "advisory",
                f"workspace {workspace!r} can be queried for agent {agent!r}",
                f"workspace {workspace!r} could not be queried for agent {agent!r}",
                hint="check the workspace, authentication context, and Intake availability",
            )
        )
    return results
