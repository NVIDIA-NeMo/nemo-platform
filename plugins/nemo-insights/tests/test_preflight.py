# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
from pathlib import Path

import httpx
import pytest
from nemo_insights_plugin import preflight
from nemo_insights_plugin.contracts.checks import format_report, required_failures
from nemo_insights_plugin.preflight import (
    AnalysisProbes,
    check_agent_spec,
    check_environment,
    check_profile,
)
from nemo_insights_plugin.profile import AnalysisProfile
from nemo_platform import NeMoPlatformError


async def always_queryable(base_url: str, workspace: str, agent: str) -> bool:
    return True


async def never_queryable(base_url: str, workspace: str, agent: str) -> bool:
    return False


def test_missing_inference_key_is_required_failure(tmp_path: Path) -> None:
    results = asyncio.run(
        check_environment(
            agent="a",
            workspace="default",
            base_url="http://localhost:8080",
            profile_dir=tmp_path,
            probes=AnalysisProbes(
                env={},
                http_ok=lambda base_url: True,
                workspace_ok=always_queryable,
            ),
        )
    )

    assert any(result.name == "INFERENCE_API_KEY" and result.status == "fail" for result in results)
    assert required_failures(results)


def test_workspace_query_failure_is_advisory(tmp_path: Path) -> None:
    results = asyncio.run(
        check_environment(
            agent="a",
            workspace="missing",
            base_url="http://localhost:8080",
            profile_dir=tmp_path,
            probes=AnalysisProbes(
                env={"INFERENCE_API_KEY": "k"},
                http_ok=lambda base_url: True,
                workspace_ok=never_queryable,
            ),
        )
    )

    warning = next(result for result in results if result.name == "workspace-query")
    assert warning.status == "warn"
    assert warning.severity == "advisory"


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("OIDC discovery failed", request=httpx.Request("GET", "https://platform.example")),
        NeMoPlatformError("SDK initialization failed"),
        RuntimeError("NeMoPlatform client initialization failed: invalid context"),
        ValueError("invalid remote configuration"),
        OSError("could not read SDK configuration"),
    ],
)
def test_remote_workspace_probe_treats_client_construction_failures_as_advisory(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    def fail_to_construct(base_url: str) -> object:
        raise error

    monkeypatch.setattr(preflight, "make_client", fail_to_construct)

    assert asyncio.run(preflight._default_workspace_ok("https://platform.example", "default", "agent")) is False


def test_profile_and_agent_spec_failures_are_required(tmp_path: Path) -> None:
    profile_results = check_profile(None, None)
    spec_results = check_agent_spec(None, "configured agent spec does not exist")

    assert required_failures(profile_results) == profile_results
    assert required_failures(spec_results) == spec_results


def test_agent_spec_invalid_utf8_is_required_failure(tmp_path: Path) -> None:
    spec = tmp_path / "AGENT-SPEC.md"
    spec.write_bytes(b"\xff\xfe")

    results = check_agent_spec(spec, None)

    assert results[0].status == "fail"
    assert results[0].severity == "required"
    assert "UTF-8" in results[0].message
    assert results[0].hint == "ensure the file is readable and encoded as UTF-8"


def test_agent_spec_unreadable_is_required_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = tmp_path / "AGENT-SPEC.md"
    spec.write_text("# Agent", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_spec_read(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if path == spec:
            raise PermissionError("permission denied")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", deny_spec_read)

    results = check_agent_spec(spec, None)

    assert results[0].status == "fail"
    assert results[0].severity == "required"
    assert "permission denied" in results[0].message
    assert results[0].hint == "ensure the file is readable and encoded as UTF-8"


def test_healthy_setup_formats_grouped_report(tmp_path: Path) -> None:
    profile = AnalysisProfile(agent="a", profile_dir=tmp_path)
    (tmp_path / "AGENT-SPEC.md").write_text("# Agent", encoding="utf-8")
    results = check_profile(profile, None) + check_agent_spec(tmp_path / "AGENT-SPEC.md", None)
    results += asyncio.run(
        check_environment(
            agent="a",
            workspace="default",
            base_url="http://localhost:8080",
            profile_dir=tmp_path,
            probes=AnalysisProbes(
                env={"INFERENCE_API_KEY": "k"},
                http_ok=lambda base_url: True,
                workspace_ok=always_queryable,
            ),
        )
    )

    report = format_report(results)

    assert "Profile\n  ✓ profile for agent 'a'" in report
    assert "Credentials\n  ✓ INFERENCE_API_KEY set" in report
    assert "Platform\n  ✓ http://localhost:8080 reachable" in report
    assert not required_failures(results)
