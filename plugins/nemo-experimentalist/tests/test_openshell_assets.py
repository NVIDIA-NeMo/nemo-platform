# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
OPENSHELL_ROOT = PLUGIN_ROOT / "src" / "nemo_experimentalist_plugin" / "openshell"
POLICY_PATH = OPENSHELL_ROOT / "policy.yaml"
DOCKER_DESKTOP_POLICY_PATH = OPENSHELL_ROOT / "policy.docker-desktop.yaml"
LAUNCHER_PATH = OPENSHELL_ROOT / "launcher.py"
RUNNER_PATH = OPENSHELL_ROOT / "run.sh"
FULL_RUN_SMOKE_PATH = OPENSHELL_ROOT / "smoke-full-run.sh"
PROVIDER_SETUP_PATH = OPENSHELL_ROOT / "configure-providers.sh"
ASKPASS_PATH = OPENSHELL_ROOT / "git-askpass.sh"
PROVIDER_PROFILE_DIR = OPENSHELL_ROOT / "provider-profiles"
DOCKERFILE_PATH = PLUGIN_ROOT / "Dockerfile"
DOCKER_BAKE_PATH = REPO_ROOT / "docker-bake.hcl"


def test_openshell_policy_fails_closed_without_docker_access() -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["landlock"]["compatibility"] == "hard_requirement"
    assert policy["process"] == {"run_as_user": "sandbox", "run_as_group": "sandbox"}
    assert "/dev/urandom" in policy["filesystem_policy"]["read_only"]
    serialized = POLICY_PATH.read_text(encoding="utf-8").lower()
    assert "docker.sock" not in serialized
    assert "docker_host" not in serialized
    assert set(policy["network_policies"]) == {"nemo_platform"}
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
    docker_bake = DOCKER_BAKE_PATH.read_text(encoding="utf-8")

    assert "iproute2" in dockerfile
    assert "nftables" in dockerfile
    assert "gh" in dockerfile
    assert "glab" in dockerfile
    assert "nemo-experimentalist-git-askpass" in dockerfile
    assert "touch /etc/nemo-experimentalist-container" in dockerfile
    assert "USER sandbox" in dockerfile
    assert 'com.nvidia.nemo.experimentalist.openshell-runtime="1"' in dockerfile
    assert "docker.sock" not in dockerfile
    assert "docker-ce-cli" not in dockerfile
    assert 'dockerfile = "plugins/nemo-experimentalist/Dockerfile"' in docker_bake


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
    assert 'source_control="${NEMO_EXPERIMENTALIST_SOURCE_CONTROL:-none}"' in runner
    assert 'create_args+=(--provider "$source_provider")' in runner
    assert "github-read | github-publish | gitlab-read | gitlab-publish" in runner
    assert "NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER" not in runner
    assert "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL" in runner
    assert "GIT_ASKPASS=/usr/local/bin/nemo-experimentalist-git-askpass" in runner
    assert "GIT_TERMINAL_PROMPT=0" in runner
    assert "GH_PROMPT_DISABLED=1" in runner
    assert "GLAB_NO_PROMPT=1" in runner
    assert 'create_args+=(--env "GITLAB_HOST=$gitlab_host")' in runner
    assert 'glab config set token "$GITLAB_TOKEN" --host "$GITLAB_HOST"' in runner
    assert 'glab config set git_protocol https --host "$GITLAB_HOST"' in runner
    assert 'remote_workspace="/sandbox/project/$(basename "$workspace_dir")"' in runner
    assert "/app/.venv/bin/nemo experimentalist" in runner
    assert "--runtime" not in runner
    assert "local/nmp-experimentalist:local" in runner
    assert "--no-git-ignore" not in runner
    assert "command -v docker" in runner
    assert "/var/run/docker.sock" in runner
    assert LAUNCHER_PATH.is_file()


def test_provider_setup_imports_scoped_profiles_and_keeps_inference_on_gateway() -> None:
    setup = PROVIDER_SETUP_PATH.read_text(encoding="utf-8")

    assert "provider profile lint" in setup
    assert "provider profile import" in setup
    assert "provider profile delete" in setup
    assert "providers_v2_enabled" in setup
    assert "NEMO_EXPERIMENTALIST_GITLAB_HOST" in setup
    assert "host: gitlab\\\\.com" in setup
    assert "nemo-experimentalist-harbor-bridge" in setup
    assert "nemo-experimentalist-github-read" in setup
    assert "nemo-experimentalist-github-publish" in setup
    assert "nemo-experimentalist-gitlab-read" in setup
    assert "nemo-experimentalist-gitlab-publish" in setup
    assert "openshell inference set" in setup
    assert "--from-existing" in setup
    assert "NVIDIA_BASE_URL=https://inference-api.nvidia.com/v1" in setup
    assert '--credential "$credential_env"' in setup


def test_provider_setup_deletes_platform_scoped_profiles(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    openshell_log = tmp_path / "openshell.log"
    fake_openshell = fake_bin / "openshell"
    fake_openshell.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >>"$FAKE_OPENSHELL_LOG"
if [[ "$1 $2" == "provider get" ]]; then
  exit 1
fi
if [[ "$1 $2 $3" == "provider profile export" ]]; then
  printf 'id: %s\\nscope: platform\\n' "$4"
fi
""",
        encoding="utf-8",
    )
    fake_openshell.chmod(0o755)

    result = subprocess.run(
        ["bash", str(PROVIDER_SETUP_PATH)],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ
        | {
            "FAKE_OPENSHELL_LOG": str(openshell_log),
            "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN": "bridge-placeholder",
            "NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR": str(tmp_path / "profiles"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
    )

    assert result.returncode == 0, result.stderr
    log = openshell_log.read_text(encoding="utf-8")
    for profile_path in PROVIDER_PROFILE_DIR.glob("*.yaml"):
        assert f"provider profile delete --global {profile_path.stem}" in log


def test_provider_setup_derives_raw_inference_hub_model_id(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    openshell_log = tmp_path / "openshell.log"
    fake_openshell = fake_bin / "openshell"
    fake_openshell.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >>"$FAKE_OPENSHELL_LOG"
if [[ "$1 $2" == "provider get" || "$1 $2 $3" == "provider profile export" ]]; then
  exit 1
fi
""",
        encoding="utf-8",
    )
    fake_openshell.chmod(0o755)
    env = os.environ.copy()
    env.pop("NEMO_EXPERIMENTALIST_INFERENCE_MODEL", None)
    env |= {
        "EXPERIMENTALIST_SMART_MODEL_NAME": "openai/aws/anthropic/claude-haiku-4-5-v1",
        "FAKE_OPENSHELL_LOG": str(openshell_log),
        "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN": "bridge-placeholder",
        "NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR": str(tmp_path / "profiles"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }

    result = subprocess.run(
        ["bash", str(PROVIDER_SETUP_PATH)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log = openshell_log.read_text(encoding="utf-8")
    assert "inference set --provider nemo-experimentalist-inference --model aws/anthropic/claude-haiku-4-5-v1" in log


def test_source_control_profiles_separate_read_and_publish_authority() -> None:
    profiles = {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) for path in PROVIDER_PROFILE_DIR.glob("*.yaml")
    }

    assert set(profiles) == {
        "nemo-experimentalist-github-publish",
        "nemo-experimentalist-github-read",
        "nemo-experimentalist-gitlab-publish",
        "nemo-experimentalist-gitlab-read",
        "nemo-experimentalist-harbor-bridge",
    }
    for name, profile in profiles.items():
        assert profile["id"] == name

    github_read = profiles["nemo-experimentalist-github-read"]
    github_publish = profiles["nemo-experimentalist-github-publish"]
    github_read_git = next(endpoint for endpoint in github_read["endpoints"] if endpoint["host"] == "github.com")
    github_publish_git = next(endpoint for endpoint in github_publish["endpoints"] if endpoint["host"] == "github.com")
    github_read_posts = {
        rule["allow"]["path"] for rule in github_read_git["rules"] if rule["allow"]["method"] == "POST"
    }
    github_publish_posts = {
        rule["allow"]["path"] for rule in github_publish_git["rules"] if rule["allow"]["method"] == "POST"
    }
    assert github_read_posts == {"/**/git-upload-pack"}
    assert github_publish_posts == {"/**/git-upload-pack", "/**/git-receive-pack"}

    github_read_graphql = next(endpoint for endpoint in github_read["endpoints"] if endpoint["protocol"] == "graphql")
    github_publish_graphql = next(
        endpoint for endpoint in github_publish["endpoints"] if endpoint["protocol"] == "graphql"
    )
    assert {rule["allow"]["operation_type"] for rule in github_read_graphql["rules"]} == {"query"}
    assert github_publish_graphql["rules"][-1]["allow"] == {
        "operation_type": "mutation",
        "operation_name": "PullRequestCreate*",
    }

    gitlab_read = profiles["nemo-experimentalist-gitlab-read"]
    gitlab_publish = profiles["nemo-experimentalist-gitlab-publish"]
    gitlab_read_posts = {
        rule["allow"]["path"] for rule in gitlab_read["endpoints"][0]["rules"] if rule["allow"]["method"] == "POST"
    }
    gitlab_publish_posts = {
        rule["allow"]["path"] for rule in gitlab_publish["endpoints"][0]["rules"] if rule["allow"]["method"] == "POST"
    }
    assert gitlab_read_posts == {"/**/git-upload-pack"}
    assert gitlab_publish_posts == {
        "/**/git-upload-pack",
        "/**/git-receive-pack",
        "/api/v4/projects/**/merge_requests",
    }


def test_harbor_bridge_profile_has_only_bounded_evaluation_and_dependency_contracts() -> None:
    profile = yaml.safe_load(
        (PROVIDER_PROFILE_DIR / "nemo-experimentalist-harbor-bridge.yaml").read_text(encoding="utf-8")
    )
    endpoint = profile["endpoints"][0]

    assert endpoint["host"] == "host.docker.internal"
    assert endpoint["port"] == 8765
    assert [rule["allow"] for rule in endpoint["rules"]] == [
        {"method": "GET", "path": "/health/ready"},
        {"method": "POST", "path": "/v1/evaluations"},
        {"method": "POST", "path": "/v1/dependencies"},
        {"method": "POST", "path": "/v1/dependencies/*/exec"},
        {"method": "DELETE", "path": "/v1/dependencies/*"},
    ]


def test_openshell_shell_assets_parse() -> None:
    for path in (RUNNER_PATH, FULL_RUN_SMOKE_PATH, PROVIDER_SETUP_PATH, ASKPASS_PATH):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_full_run_smoke_invokes_normal_runtime_and_rejects_degraded_analysis() -> None:
    smoke = FULL_RUN_SMOKE_PATH.read_text(encoding="utf-8")

    assert '"$nemo_bin" experimentalist run --experiment-dir "$smoke_output" "$@"' in smoke
    assert "eval-and-optimize/analysis/round-*.md" in smoke
    assert "analysis_error" in smoke


def test_git_askpass_uses_provider_placeholders() -> None:
    github_env = os.environ | {"GH_TOKEN": "github-placeholder"}
    gitlab_env = os.environ | {
        "GITLAB_HOST": "gitlab.example.com",
        "GITLAB_TOKEN": "gitlab-placeholder",
    }

    github = subprocess.run(
        ["bash", str(ASKPASS_PATH), "Password for 'https://github.com':"],
        check=True,
        capture_output=True,
        text=True,
        env=github_env,
    )
    gitlab = subprocess.run(
        ["bash", str(ASKPASS_PATH), "Password for 'https://gitlab.example.com':"],
        check=True,
        capture_output=True,
        text=True,
        env=gitlab_env,
    )

    assert github.stdout.strip() == "github-placeholder"
    assert gitlab.stdout.strip() == "gitlab-placeholder"
