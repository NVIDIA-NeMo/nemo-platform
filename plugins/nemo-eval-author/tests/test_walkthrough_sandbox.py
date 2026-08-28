# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_WALKTHROUGH_RHO = Path(__file__).resolve().parents[1] / "walkthrough" / "rho-agent"
if str(_WALKTHROUGH_RHO) not in sys.path:
    sys.path.insert(0, str(_WALKTHROUGH_RHO))

from prepare_sandbox import (  # noqa: E402
    ASSETS,
    IMAGE_REF,
    RHO_REVISION,
    clone_rho_agent,
    cover_read_task_toml,
    inference_allowlist_hosts,
    render_job_config,
    sandbox_task_toml,
    task_0_task_toml,
    write_baseline_overlay,
)


def test_clone_rho_agent_checks_out_pinned_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prepare_sandbox._run", fake_run)

    checkout = clone_rho_agent(tmp_path / "ws")
    assert checkout == tmp_path / "ws" / "rho-agent"
    assert calls[0][:2] == ["git", "clone"]
    assert calls[1] == ["git", "-C", str(checkout), "checkout", RHO_REVISION]


def test_clone_rho_agent_skips_when_revision_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / "ws" / "rho-agent"
    checkout.mkdir(parents=True)

    def fake_run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "-C", str(checkout)]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=f"{RHO_REVISION}\n",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("prepare_sandbox._run", fake_run)
    monkeypatch.setattr(
        "prepare_sandbox.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=(), returncode=0, stdout=f"{RHO_REVISION}\n", stderr=""
        ),
    )

    assert clone_rho_agent(tmp_path / "ws") == checkout


def test_inference_allowlist_hosts_from_base_url() -> None:
    hosts = inference_allowlist_hosts("https://inference.example.com/v1")
    assert hosts == ["inference.example.com"]


def test_inference_allowlist_hosts_default() -> None:
    hosts = inference_allowlist_hosts("")
    assert "inference-api.nvidia.com" in hosts


def test_default_rho_agent_model_is_qwen() -> None:
    import os

    assert os.environ["DEFAULT_RHO_AGENT_MODEL"] == "openai/nvidia/qwen/qwen3.5-122b-a10b"


def test_litellm_model_for_openai_compatible_gateway() -> None:
    from rho_harbor_agent import litellm_model_for_openai_compatible_gateway  # noqa: E402

    assert (
        litellm_model_for_openai_compatible_gateway("nvidia/qwen/qwen3.5-122b-a10b")
        == "openai/nvidia/qwen/qwen3.5-122b-a10b"
    )
    assert (
        litellm_model_for_openai_compatible_gateway("openai/nvidia/qwen/qwen3.5-122b-a10b")
        == "openai/nvidia/qwen/qwen3.5-122b-a10b"
    )
    assert litellm_model_for_openai_compatible_gateway("openai/gpt-5-mini") == "openai/gpt-5-mini"


def test_sandbox_task_toml_sets_network_policy() -> None:
    toml = sandbox_task_toml(inference_hosts=["inference-api.nvidia.com"])
    assert 'network_mode = "no-network"' in toml
    assert 'network_mode = "allowlist"' in toml
    assert "inference-api.nvidia.com" in toml


def test_check_egress_control_support_accepts_harbor_probe_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_sandbox import check_egress_control_support  # noqa: E402

    monkeypatch.setattr("prepare_sandbox._harbor_egress_kernel_support", lambda: None)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=(), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prepare_sandbox.subprocess.run", fake_run)
    payload = check_egress_control_support()
    assert payload["supported"] is True
    assert payload["method"] == "docker-probe"
    assert "CONFIG_NFT_FIB_INET" in payload["reason"]


def test_check_egress_control_support_prefers_harbor_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_sandbox import check_egress_control_support  # noqa: E402

    monkeypatch.setattr("prepare_sandbox._harbor_egress_kernel_support", lambda: True)
    monkeypatch.setattr("prepare_sandbox._docker_desktop_version", lambda: None)

    def fake_run(command: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "container"]:
            raise AssertionError("docker egress probe should be skipped when harbor API is available")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("prepare_sandbox.subprocess.run", fake_run)
    payload = check_egress_control_support()
    assert payload["supported"] is True
    assert payload["method"] == "harbor"


def test_check_egress_control_support_reports_missing_nft_inet(monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_sandbox import check_egress_control_support  # noqa: E402

    monkeypatch.setattr("prepare_sandbox._harbor_egress_kernel_support", lambda: None)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=(), returncode=1, stdout="", stderr="")

    monkeypatch.setattr("prepare_sandbox.subprocess.run", fake_run)
    payload = check_egress_control_support()
    assert payload["supported"] is False
    assert "CONFIG_NFT_FIB_INET" in payload["reason"]


def test_prepare_workspace_requires_egress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_sandbox import PrepareError, prepare_workspace  # noqa: E402

    monkeypatch.setattr(
        "prepare_sandbox.check_egress_control_support",
        lambda: {"supported": False, "reason": "probe failed"},
    )
    monkeypatch.setattr("prepare_sandbox.build_agent_image", lambda **kwargs: IMAGE_REF)

    with pytest.raises(PrepareError, match="requires Harbor network allowlists"):
        prepare_workspace(tmp_path / "ws", build_image=False)


def test_task_0_task_toml_names_task() -> None:
    toml = task_0_task_toml(inference_hosts=["example.com"])
    assert 'name = "rho-agent/task-0"' in toml
    assert "example.com" in toml


def test_cover_read_task_toml_names_task() -> None:
    toml = cover_read_task_toml(inference_hosts=["example.com"])
    assert 'name = "rho-agent/cover-read"' in toml
    assert "example.com" in toml


def test_render_job_config_includes_extra_allowed_hosts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    task = workspace / ".eval-author" / "sandbox" / "task-0"
    task.mkdir(parents=True)
    (task / "instruction.md").write_text("hello", encoding="utf-8")

    payload = render_job_config(
        job_name="demo",
        jobs_dir=workspace / ".eval-author" / "baseline-jobs",
        task_path=task,
        fixture=workspace,
        n_attempts=1,
        inference_hosts=["inference-api.nvidia.com"],
    )
    assert payload["agents"][0]["extra_allowed_hosts"] == ["inference-api.nvidia.com"]
    assert payload["tasks"][0]["path"] == ".eval-author/sandbox/task-0"


def test_write_baseline_overlay_from_bundled_task(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    overlay = write_baseline_overlay(workspace, image_ref=IMAGE_REF, inference_hosts=["example.com"])
    assert overlay.is_dir()
    assert (overlay / "instruction.md").is_file()
    assert (overlay / "tests" / "test.sh").is_file()
    dockerfile = (overlay / "environment" / "Dockerfile").read_text(encoding="utf-8")
    assert IMAGE_REF.split(":")[0] in dockerfile
    task_toml = (overlay / "task.toml").read_text(encoding="utf-8")
    assert 'name = "rho-agent/task-0"' in task_toml
    assert "example.com" in task_toml


def test_bundled_task_0_assets_exist() -> None:
    task_root = ASSETS / "task-0"
    assert (task_root / "instruction.md").is_file()
    assert (task_root / "environment" / "Dockerfile").is_file()
    assert (task_root / "tests" / "test.sh").is_file()
    assert (task_root / "solution" / "solve.sh").is_file()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://custom.gateway.example/v1", "custom.gateway.example"),
        ("http://127.0.0.1:8080/v1", "127.0.0.1"),
    ],
)
def test_inference_host_parsing(url: str, expected: str) -> None:
    assert inference_allowlist_hosts(url) == [expected]
