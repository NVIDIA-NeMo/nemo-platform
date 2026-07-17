# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[3]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yaml"
NODE_BINARY = os.environ.get("NODE_BINARY", "node")
NIGHTLY_REGISTRY = "ghcr.io/nvidia-nemo/nemo-platform"
STABLE_REGISTRY = "nvcr.io/nvidia/nemo-platform"


def _notify_end_step() -> dict:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())
    return next(step for step in workflow["jobs"]["notify-end"]["steps"] if step["name"] == "Send Slack alert")


def _run_notify_end_script(*, release_type: str, release_label: str, containers: list[str]) -> dict:
    script = _notify_end_step()["with"]["script"]
    runner = f"""
globalThis.core = {{setFailed(message) {{ throw new Error(message); }}}};
globalThis.fetch = async (url, options) => {{
  process.stdout.write(JSON.stringify({{url, payload: JSON.parse(options.body)}}));
  return {{ok: true, status: 200}};
}};
(async () => {{
{script}
}})().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
    """
    env = os.environ | {
        "SLACK_ALERTS_WEBHOOK": "https://hooks.slack.test/alerts",
        "SLACK_RELEASE_WEBHOOK": "https://hooks.slack.test/releases",
        "RELEASE_TYPE": release_type,
        "RELEASE_LABEL": release_label,
        "SOURCE_SHA": "0123456789abcdef0123456789abcdef01234567",
        "COMMIT_URL": ("https://github.com/NVIDIA-NeMo/nemo-platform/commit/0123456789abcdef0123456789abcdef01234567"),
        "WHEEL_IDS": "[]",
        "WHEEL_CATALOG": "[]",
        "WHEEL_VERSION": "1.2.3",
        "CONTAINER_IDS": json.dumps(containers),
        "INCLUDE_HELM": "false",
        "CHART_VERSION": "1.2.3",
        "NIGHTLY_WHEEL_INDEX": "https://pypi.nvidia.com/nemo-platform-nightly/simple",
        "STABLE_WHEEL_INDEX": "https://pypi.nvidia.com/nemo-platform/simple",
        "NGC_CATALOG_BASE": "https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo",
        "RELEASE_NIGHTLY_CONTAINER_REGISTRY": NIGHTLY_REGISTRY,
        "RELEASE_STABLE_CONTAINER_REGISTRY": STABLE_REGISTRY,
        "POLL_RESULT": "success",
        "GITHUB_RELEASE_RESULT": "success",
        "DEPLOYMENT_RESULT": "success",
        "RUN_URL": "https://github.com/NVIDIA-NeMo/nemo-platform/actions/runs/123",
        "RUN_NUMBER": "456",
    }
    result = subprocess.run(
        [NODE_BINARY, "-e", runner],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return json.loads(result.stdout)


def test_notify_end_step_passes_container_registry_constants() -> None:
    step_env = _notify_end_step()["env"]

    assert step_env["RELEASE_NIGHTLY_CONTAINER_REGISTRY"] == ("${{ env.RELEASE_NIGHTLY_CONTAINER_REGISTRY }}")
    assert step_env["RELEASE_STABLE_CONTAINER_REGISTRY"] == ("${{ env.RELEASE_STABLE_CONTAINER_REGISTRY }}")


@pytest.mark.parametrize(
    ("release_type", "release_label", "containers", "title", "expected_refs"),
    [
        (
            "nightly",
            "nightly-20260716040726",
            ["nmp-api", "nmp-cpu-tasks"],
            "*:crescent_moon: Nightly release publish complete*",
            [
                f"{NIGHTLY_REGISTRY}/nmp-api:nightly-20260716040726",
                f"{NIGHTLY_REGISTRY}/nmp-cpu-tasks:nightly-20260716040726",
            ],
        ),
        (
            "stable",
            "1.2.3",
            ["nmp-api"],
            "*:ship: Release publish complete*",
            [f"{STABLE_REGISTRY}/nmp-api:1.2.3"],
        ),
    ],
)
def test_notify_end_renders_copyable_container_refs(
    release_type: str,
    release_label: str,
    containers: list[str],
    title: str,
    expected_refs: list[str],
) -> None:
    request = _run_notify_end_script(
        release_type=release_type,
        release_label=release_label,
        containers=containers,
    )

    expected_text = "\n".join(
        [
            title,
            f"Release: {release_label}",
            "Commit: <https://github.com/NVIDIA-NeMo/nemo-platform/commit/"
            "0123456789abcdef0123456789abcdef01234567|0123456>",
            "",
            "*Artifacts published:*",
            "*:docker_: Containers published:*",
            "```",
            *expected_refs,
            "```",
            "",
            ":link: <https://github.com/NVIDIA-NeMo/nemo-platform/actions/runs/123|Release run #456>",
        ]
    )
    assert request == {
        "url": "https://hooks.slack.test/releases",
        "payload": {"text": expected_text},
    }


def test_notify_end_omits_container_section_when_no_containers() -> None:
    request = _run_notify_end_script(
        release_type="nightly",
        release_label="nightly-20260716040726",
        containers=[],
    )

    assert request["payload"]["text"] == "\n".join(
        [
            "*:crescent_moon: Nightly release publish complete*",
            "Release: nightly-20260716040726",
            "Commit: <https://github.com/NVIDIA-NeMo/nemo-platform/commit/"
            "0123456789abcdef0123456789abcdef01234567|0123456>",
            "",
            "*Artifacts published:*",
            "",
            ":link: <https://github.com/NVIDIA-NeMo/nemo-platform/actions/runs/123|Release run #456>",
        ]
    )
    assert "Containers published" not in request["payload"]["text"]
    assert "```" not in request["payload"]["text"]
