# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
POLICY_PATH = PLUGIN_ROOT / "examples" / "openshell" / "policy.yaml"
DOCKER_DESKTOP_POLICY_PATH = PLUGIN_ROOT / "examples" / "openshell" / "policy.docker-desktop.yaml"
RUNNER_PATH = PLUGIN_ROOT / "examples" / "openshell" / "run.sh"
DOCKERFILE_PATH = REPO_ROOT / "docker" / "Dockerfile.nmp-experimentalist"


def test_openshell_policy_fails_closed_without_docker_access() -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["landlock"]["compatibility"] == "hard_requirement"
    assert policy["process"] == {"run_as_user": "sandbox", "run_as_group": "sandbox"}
    assert "/dev/urandom" in policy["filesystem_policy"]["read_only"]
    serialized = POLICY_PATH.read_text(encoding="utf-8").lower()
    assert "docker.sock" not in serialized
    assert "docker_host" not in serialized
    assert set(policy["network_policies"]) == {"harbor_bridge", "nemo_platform"}
    endpoint = policy["network_policies"]["nemo_platform"]["endpoints"][0]
    assert "access" not in endpoint
    assert endpoint["rules"] == [{"allow": {"method": "GET", "path": "/health/ready"}}]
    binaries = {item["path"] for item in policy["network_policies"]["nemo_platform"]["binaries"]}
    assert "/usr/local/bin/python3.13" in binaries


def test_docker_desktop_policy_is_an_explicit_landlock_fallback() -> None:
    strict = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    development = yaml.safe_load(DOCKER_DESKTOP_POLICY_PATH.read_text(encoding="utf-8"))

    assert development["landlock"]["compatibility"] == "best_effort"
    assert development["filesystem_policy"] == strict["filesystem_policy"]
    assert development["process"] == strict["process"]
    assert development["network_policies"] == strict["network_policies"]


def test_experimentalist_image_has_no_docker_client_or_socket() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "iproute2" in dockerfile
    assert "nftables" in dockerfile
    assert "USER sandbox" in dockerfile
    assert "docker.sock" not in dockerfile
    assert "docker-ce-cli" not in dockerfile


def test_openshell_launcher_uses_policy_and_inference_route() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")

    assert '--policy "$policy_path"' in runner
    assert "command -v openshell" in runner
    assert "EXPERIMENTALIST_API_BASE=https://inference.local/v1" in runner
    assert "host.docker.internal:8080" in runner
    assert 'sandbox_name="${NEMO_EXPERIMENTALIST_SANDBOX_NAME:-nemo-exp-$$}"' in runner
    assert "NEMO_EXPERIMENTALIST_POLICY_MODE" in runner
    assert "policy.docker-desktop.yaml" in runner
    assert '--provider "$bridge_provider"' in runner
    assert "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL" in runner
    assert 'remote_workspace="/sandbox/project/$(basename "$workspace_dir")"' in runner
    assert "/app/.venv/bin/nemo experimentalist" in runner
    assert "docker.sock" not in runner
