# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenShell preparation, launcher, entrypoint, and policy tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import DatasetRef
from nemo_experimentalist_plugin.experimentalist.run import run_experimentalist
from nemo_experimentalist_plugin.harbor_bridge.contracts import BridgeRuntimeConfig
from nemo_experimentalist_plugin.openshell import inner, launcher
from nemo_experimentalist_plugin.openshell.preparation import (
    PreparedOpenShellRun,
    SandboxRunManifest,
    prepare_openshell_run,
)
from nemo_experimentalist_plugin.resolve import ResolvedExperimentInputs

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
OPEN_SHELL_ROOT = PLUGIN_ROOT / "src" / "nemo_experimentalist_plugin" / "openshell"


def _task_dataset(path: Path, name: str) -> Path:
    task = path / name
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "task.toml").write_text(
        f'[task]\nname = "fixture/{name}"\n[environment]\ntype = "docker"\n[verifier]\n',
        encoding="utf-8",
    )
    (task / "instruction.md").write_text("trusted\n", encoding="utf-8")
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (task / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (task / "nemo-task-envelope.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_data": [{"path": "instruction.md", "media_type": "text/plain", "max_bytes": 1000}],
                "verifier_paths": ["tests/test.sh"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _resolved_inputs(tmp_path: Path) -> ResolvedExperimentInputs:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "main.py").write_text("print('agent')\n", encoding="utf-8")
    train = _task_dataset(tmp_path / "train", "train-task")
    validation = _task_dataset(tmp_path / "validation", "validation-task")
    template = _task_dataset(tmp_path / "template", "template-task")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "SKILL.md").write_text("# Fixture\n", encoding="utf-8")
    return ResolvedExperimentInputs(
        agent=str(agent),
        agent_spec=None,
        insight=None,
        train_dataset=DatasetRef(uri=str(train), metadata={"id": "train"}),
        validation_dataset=DatasetRef(uri=str(validation), metadata={"id": "validation"}),
        task_template=DatasetRef(uri=str(template), metadata={"id": "task-template"}),
        workspace="default",
        config=EvolutionaryOptimizerConfig(max_rounds=1, storage={"publish_winner": False}),
        framework_skills_dirs=[skills],
    )


async def test_preparation_copies_only_credential_free_inputs_and_separates_catalog(tmp_path: Path) -> None:
    inputs = _resolved_inputs(tmp_path)
    secret = tmp_path / "host-secret.txt"
    secret.write_text("do-not-copy", encoding="utf-8")

    prepared = await prepare_openshell_run(
        inputs,
        experiment_dir=tmp_path / "experiment",
        client=None,
    )

    manifest = SandboxRunManifest.model_validate_json(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest.agent == "agent"
    assert manifest.train_dataset == "datasets/train"
    assert manifest.config.storage.publish_winner is False
    assert not (prepared.sandbox_input / ".git").exists()
    assert not (prepared.sandbox_input / secret.name).exists()
    assert "do-not-copy" not in prepared.manifest_path.read_text(encoding="utf-8")

    sandbox_instruction = prepared.sandbox_input / "datasets" / "train" / "train-task" / "instruction.md"
    sandbox_instruction.write_text("sandbox overlay\n", encoding="utf-8")
    catalog_instruction = next(prepared.catalog_root.glob("envelopes/*/dataset/train-task/instruction.md"))
    assert catalog_instruction.read_text(encoding="utf-8") == "trusted\n"


async def test_preparation_rejects_source_control_publishing(tmp_path: Path) -> None:
    inputs = _resolved_inputs(tmp_path)
    inputs.config.storage.publish_winner = True

    with pytest.raises(ValueError, match="does not support source-control"):
        await prepare_openshell_run(inputs, experiment_dir=tmp_path / "experiment", client=None)


async def test_preparation_rejects_linked_agent_spec(tmp_path: Path) -> None:
    inputs = _resolved_inputs(tmp_path)
    source = tmp_path / "AGENT-SPEC-source.md"
    source.write_text("# Agent\n", encoding="utf-8")
    linked = tmp_path / "AGENT-SPEC.md"
    linked.symlink_to(source)
    inputs.agent_spec = str(linked)

    with pytest.raises(ValueError, match="must not be linked"):
        await prepare_openshell_run(inputs, experiment_dir=tmp_path / "experiment", client=None)

    assert not (tmp_path / "experiment" / "openshell-runtime").exists()


async def test_inner_entrypoint_runs_only_with_marker_and_prepared_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = await prepare_openshell_run(
        _resolved_inputs(tmp_path),
        experiment_dir=tmp_path / "experiment",
        client=None,
    )
    captured: dict[str, Any] = {}

    async def record_run(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "inner-summary"

    class _Client:
        async def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        "nemo_experimentalist_plugin.experimentalist.run.run_experimentalist",
        record_run,
    )
    monkeypatch.setattr(inner, "make_client", lambda value: _Client())
    monkeypatch.setenv("NEMO_EXPERIMENTALIST_OPEN_SHELL_RUNTIME", "1")
    monkeypatch.setenv("NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL", "http://host.openshell.internal:8765")
    monkeypatch.setenv(
        "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
        "provider-OPENSHELL-RESOLVE-ENV-NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
    )

    result = await inner.run_prepared_manifest(
        prepared.manifest_path,
        output_dir=tmp_path / "sandbox-output",
    )

    assert result == "inner-summary"
    assert Path(captured["agent"]).is_relative_to(prepared.sandbox_input)
    assert cast(DatasetRef, captured["train_dataset"]).uri.startswith("file:")
    assert captured["closed"] is True


def test_launcher_fails_closed_when_openshell_is_missing(tmp_path: Path) -> None:
    prepared = PreparedOpenShellRun(
        root=tmp_path,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    prepared.manifest_path.parent.mkdir()
    prepared.manifest_path.write_text(
        SandboxRunManifest(
            agent="agent",
            train_dataset="datasets/train",
            validation_dataset="datasets/validation",
            workspace="default",
            config=EvolutionaryOptimizerConfig(),
            framework_skills_dirs=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(launcher.OpenShellLaunchError, match="required"):
        launcher.launch_openshell_run(
            prepared,
            experiment_dir=tmp_path / "output",
            platform_url="http://localhost:8080",
            env={"PATH": ""},
        )


def test_runtime_requires_explicit_platform_settings() -> None:
    with pytest.raises(launcher.OpenShellLaunchError, match="NEMO_DEFAULT_MODEL"):
        launcher._validate_runtime_settings({})

    runtime_env = {
        "NEMO_DEFAULT_MODEL": "openai/openai/gpt-5-mini",
        "NEMO_FAST_MODEL": "openai/openai/gpt-5-mini",
        "INFERENCE_API_KEY": "candidate-key",
        "INFERENCE_API_BASE": "https://inference-api.nvidia.com/v1",
        "AUT_MODEL_NAME": "openai/openai/gpt-5-mini",
    }
    launcher._validate_runtime_settings(runtime_env)


def test_configure_providers_passes_only_bridge_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = PreparedOpenShellRun(
        root=tmp_path,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    captured: dict[str, Any] = {}

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    runtime_env = {
        launcher.BRIDGE_TOKEN_ENV: "bridge-token-long-enough",
        launcher.BRIDGE_PROVIDER_ENV: "bridge-provider",
        "INFERENCE_API_KEY": "inference-key",
        "NEMO_DEFAULT_MODEL": "openai/openai/gpt-5-mini",
    }

    launcher._configure_providers(prepared, runtime_env)

    provider_env = cast(dict[str, str], captured["env"])
    assert provider_env[launcher.BRIDGE_TOKEN_ENV] == "bridge-token-long-enough"
    assert provider_env[launcher.BRIDGE_PROVIDER_ENV] == "bridge-provider"
    assert "INFERENCE_API_KEY" not in provider_env
    assert "NEMO_DEFAULT_MODEL" not in provider_env
    assert runtime_env["NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR"] == str(tmp_path / "host" / "provider-profiles")


@pytest.mark.parametrize(
    ("platform_url", "sandbox_url", "policy_host", "policy_port", "terminate_tls"),
    [
        ("http://platform.example:8080", "http://platform.example:8080", "platform.example", 8080, False),
        ("http://localhost:9090", "http://host.openshell.internal:9090", "host.openshell.internal", 9090, False),
        ("https://platform.example", "https://platform.example:443", "platform.example", 443, True),
    ],
)
def test_launcher_derives_policy_from_root_platform_url(
    platform_url: str,
    sandbox_url: str,
    policy_host: str,
    policy_port: int,
    terminate_tls: bool,
) -> None:
    endpoint = launcher._sandbox_platform_endpoint(platform_url)

    assert endpoint.url == sandbox_url
    assert endpoint.policy_host == policy_host
    assert endpoint.policy_port == policy_port
    assert endpoint.terminate_tls is terminate_tls


@pytest.mark.parametrize("platform_url", ["http://user@localhost:8080", "http://localhost:8080/api"])
def test_launcher_rejects_non_root_or_credentialed_platform_url(platform_url: str) -> None:
    with pytest.raises(launcher.OpenShellLaunchError, match="user information|root HTTP"):
        launcher._sandbox_platform_endpoint(platform_url)


def test_launcher_uses_custom_image_and_never_calls_local_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = PreparedOpenShellRun(
        root=tmp_path,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    prepared.sandbox_input.mkdir()
    calls: list[list[str]] = []
    stopped: list[bool] = []

    monkeypatch.setattr(launcher.shutil, "which", lambda name, *, path=None: f"/bin/{name}")
    monkeypatch.setattr(launcher, "_configure_providers", lambda *args: None)
    monkeypatch.setattr(launcher, "_delete_bridge_provider", lambda *args: True)

    class Bridge:
        def stop(self) -> None:
            stopped.append(True)

    def start_bridge(**_kwargs: Any) -> Bridge:
        return Bridge()

    def run_sandbox(script: Path, sandbox_input: Path, output: Path, policy: Path, env: dict[str, str]) -> str:
        del script, sandbox_input, output, env
        calls.append([str(policy)])
        return "sandbox-summary"

    monkeypatch.setattr(launcher.HarborBridge, "start", start_bridge)
    monkeypatch.setattr(launcher, "_run_sandbox_script", run_sandbox)

    result = launcher.launch_openshell_run(
        prepared,
        experiment_dir=tmp_path / "output",
        platform_url="http://localhost:8080",
        env={
            "PATH": "/bin",
            launcher.IMAGE_ENV: "registry.example/experimentalist:v1",
            "NEMO_DEFAULT_MODEL": "openai/openai/gpt-5-mini",
            "NEMO_FAST_MODEL": "openai/openai/gpt-5-mini",
            "INFERENCE_API_KEY": "inference-key",
            "INFERENCE_API_BASE": "https://inference-api.nvidia.com/v1",
            "AUT_MODEL_NAME": "openai/openai/gpt-5-mini",
        },
    )

    assert result == "sandbox-summary"
    assert len(calls) == 1
    assert Path(calls[0][0]).is_file()
    assert stopped == [True]


def test_default_image_build_loads_plugin_bake_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = PreparedOpenShellRun(
        root=REPO_ROOT,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if argv[1:3] == ["image", "inspect"] else 0, stdout="")

    monkeypatch.setattr(launcher.subprocess, "run", run)

    launcher._acquire_default_image(
        docker="/bin/docker",
        image=launcher.DEFAULT_IMAGE,
        prepared=prepared,
        runtime_env={launcher.PLATFORM_ENV: "linux/arm64"},
    )

    assert calls[1] == [
        "/bin/docker",
        "buildx",
        "bake",
        "-f",
        "docker-bake.hcl",
        "-f",
        "plugins/nemo-experimentalist/docker-bake.hcl",
        "nmp-experimentalist-docker",
        "--load",
    ]


def test_launcher_deletes_provider_when_configuration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = PreparedOpenShellRun(
        root=tmp_path,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    prepared.sandbox_input.mkdir()
    deleted: list[str] = []
    stopped: list[bool] = []

    monkeypatch.setattr(launcher.shutil, "which", lambda name, *, path=None: f"/bin/{name}")

    class Bridge:
        def stop(self) -> None:
            stopped.append(True)

    monkeypatch.setattr(launcher.HarborBridge, "start", lambda **_kwargs: Bridge())

    def fail_configuration(*_args: object) -> None:
        raise launcher.OpenShellLaunchError("configuration failed")

    def delete_provider(_openshell: str, env: dict[str, str]) -> bool:
        deleted.append(env[launcher.BRIDGE_PROVIDER_ENV])
        return True

    monkeypatch.setattr(launcher, "_configure_providers", fail_configuration)
    monkeypatch.setattr(launcher, "_delete_bridge_provider", delete_provider)

    with pytest.raises(launcher.OpenShellLaunchError, match="configuration failed"):
        launcher.launch_openshell_run(
            prepared,
            experiment_dir=tmp_path / "output",
            platform_url="http://localhost:8080",
            env={
                "PATH": "/bin",
                launcher.IMAGE_ENV: "registry.example/experimentalist:v1",
                "NEMO_DEFAULT_MODEL": "openai/openai/gpt-5-mini",
                "NEMO_FAST_MODEL": "openai/openai/gpt-5-mini",
                "INFERENCE_API_KEY": "inference-key",
                "INFERENCE_API_BASE": "https://inference-api.nvidia.com/v1",
                "AUT_MODEL_NAME": "openai/openai/gpt-5-mini",
            },
        )

    assert len(deleted) == 1
    assert stopped == [True]


def test_bridge_listener_uses_configured_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = PreparedOpenShellRun(
        root=tmp_path,
        catalog_root=tmp_path / "catalog",
        sandbox_input=tmp_path / "input",
        manifest_path=tmp_path / "input" / "run.json",
    )
    prepared.manifest_path.parent.mkdir()
    prepared.manifest_path.write_text(
        SandboxRunManifest(
            agent="agent",
            train_dataset="datasets/train",
            validation_dataset="datasets/validation",
            workspace="default",
            config=EvolutionaryOptimizerConfig(outcome_evaluator_config={"n_attempts": 1, "n_concurrent_trials": 256}),
            framework_skills_dirs=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    ready = iter((False, True))
    probed: list[str] = []
    captured: dict[str, Any] = {}

    class Process:
        def __init__(self) -> None:
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, timeout: int) -> int:
            del timeout
            return 0

        def kill(self) -> None:
            self.returncode = -9

    def popen(argv: list[str], **kwargs: Any) -> Process:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return Process()

    def bridge_ready(url: str) -> bool:
        probed.append(url)
        return next(ready)

    monkeypatch.setattr(launcher, "_bridge_ready", bridge_ready)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)

    managed = launcher.HarborBridge.start(
        prepared=prepared,
        runtime_env={launcher.BRIDGE_BIND_ENV: "172.18.0.1"},
    )

    assert managed is not None
    argv = cast(list[str], captured["argv"])
    assert argv[-2:] == ["--runtime-config", str(tmp_path / "host" / "bridge" / "runtime-config.json")]
    runtime_config = BridgeRuntimeConfig.model_validate_json(
        (tmp_path / "host" / "bridge" / "runtime-config.json").read_text()
    )
    assert runtime_config.host == "172.18.0.1"
    assert runtime_config.standard_attempts == 1
    assert runtime_config.standard_concurrency == 256
    assert probed == ["http://172.18.0.1:8765", "http://172.18.0.1:8765"]
    managed.stop()


def test_openshell_assets_expose_only_bounded_authority() -> None:
    strict = yaml.safe_load((OPEN_SHELL_ROOT / "policy.yaml").read_text(encoding="utf-8"))
    development = yaml.safe_load((OPEN_SHELL_ROOT / "policy.docker-desktop.yaml").read_text(encoding="utf-8"))
    provider = yaml.safe_load(
        (OPEN_SHELL_ROOT / "provider-profiles" / "nemo-experimentalist-harbor-bridge.yaml").read_text(encoding="utf-8")
    )
    configure_script = (OPEN_SHELL_ROOT / "configure-providers.sh").read_text(encoding="utf-8")
    run_script = (OPEN_SHELL_ROOT / "run.sh").read_text(encoding="utf-8")
    dockerfile = (PLUGIN_ROOT / "Dockerfile").read_text(encoding="utf-8")
    root_docker_bake = (REPO_ROOT / "docker-bake.hcl").read_text(encoding="utf-8")
    docker_bake = (PLUGIN_ROOT / "docker-bake.hcl").read_text(encoding="utf-8")

    assert strict["landlock"]["compatibility"] == "hard_requirement"
    assert development["landlock"]["compatibility"] == "best_effort"
    assert strict["filesystem_policy"] == development["filesystem_policy"]
    platform_rules = [rule["allow"] for rule in strict["network_policies"]["nemo_platform"]["endpoints"][0]["rules"]]
    assert {"method": "GET", "path": "/apis/models/v2/workspaces/**"} in platform_rules
    assert {"method": "POST", "path": "/apis/inference-gateway/v2/workspaces/**"} in platform_rules
    assert "docker.sock" not in json.dumps(strict).lower()
    assert [rule["allow"] for rule in provider["endpoints"][0]["rules"]] == [
        {"method": "GET", "path": "/health/ready"},
        {"method": "POST", "path": "/v1/evaluations"},
        {"method": "GET", "path": "/v1/evaluations/*"},
        {"method": "GET", "path": "/v1/evaluations/*/artifacts"},
        {"method": "DELETE", "path": "/v1/evaluations/*"},
        {"method": "POST", "path": "/v1/dependencies"},
        {"method": "POST", "path": "/v1/dependencies/*/exec"},
        {"method": "DELETE", "path": "/v1/dependencies/*"},
    ]
    assert '--upload "$input_dir:/sandbox/input"' in run_script
    assert "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN=" not in run_script
    assert configure_script.index("trap cleanup_failed_setup EXIT") < configure_script.index(
        'openshell provider create \\\n  --name "$bridge_provider"'
    )
    assert 'openshell provider get "$bridge_provider"' in configure_script
    assert "command -v docker" in run_script
    assert "docker.sock" not in dockerfile
    assert "USER sandbox" in dockerfile
    assert "ENTRYPOINT" not in dockerfile
    dependency_sync = dockerfile.index("--no-install-workspace")
    source_copy = dockerfile.index("COPY --from=nmp-workspace . .")
    assert dependency_sync < source_copy
    assert "COPY --from=dependencies /app/.venv /app/.venv" in dockerfile
    assert "COPY --from=builder /wheels /wheels" in dockerfile
    assert "COPY --from=builder /app/.venv" not in dockerfile
    assert 'dockerfile = "plugins/nemo-experimentalist/Dockerfile"' in docker_bake
    assert 'target "nmp-experimentalist-docker"' not in root_docker_bake


def test_openshell_shell_assets_parse() -> None:
    for name in ("run.sh", "configure-providers.sh"):
        result = subprocess.run(
            ["bash", "-n", str(OPEN_SHELL_ROOT / name)],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result.returncode == 0, result.stderr


def test_provider_setup_configures_only_the_harbor_bridge(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    openshell = fake_bin / "openshell"
    openshell.write_text(
        r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$OPENSHELL_TEST_LOG"
if [[ "$*" == provider\ profile\ export* && "${OPENSHELL_TEST_PROFILE_EXISTS:-1}" == "0" ]]; then
  exit 1
fi
""",
        encoding="utf-8",
    )
    openshell.chmod(0o755)
    command_log = tmp_path / "openshell.log"
    profile_dir = tmp_path / "profiles"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "OPENSHELL_TEST_LOG": str(command_log),
        "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN": "bridge-token",
        "NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR": str(profile_dir),
    }

    result = subprocess.run(
        [str(OPEN_SHELL_ROOT / "configure-providers.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8").splitlines()
    bridge_provider_delete = commands.index("provider delete nemo-experimentalist-harbor-bridge")
    profile_delete = commands.index("provider profile delete nemo-experimentalist-harbor-bridge")
    profile_lint = commands.index(f"provider profile lint --from {profile_dir}")
    profile_import = commands.index(f"provider profile import --from {profile_dir}")
    assert bridge_provider_delete < profile_delete < profile_lint < profile_import
    assert not any("nemo-experimentalist-inference" in command for command in commands)

    missing_profile_log = tmp_path / "missing-profile.log"
    missing_profile_env = {
        **env,
        "OPENSHELL_TEST_LOG": str(missing_profile_log),
        "OPENSHELL_TEST_PROFILE_EXISTS": "0",
    }
    missing_profile_result = subprocess.run(
        [str(OPEN_SHELL_ROOT / "configure-providers.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=missing_profile_env,
    )

    assert missing_profile_result.returncode == 0, missing_profile_result.stderr
    missing_profile_commands = missing_profile_log.read_text(encoding="utf-8").splitlines()
    profile_commands = [command for command in missing_profile_commands if command.startswith("provider profile")]
    assert profile_commands == [
        "provider profile export nemo-experimentalist-harbor-bridge -o yaml",
        f"provider profile lint --from {profile_dir}",
        f"provider profile import --from {profile_dir}",
    ]


def test_test_module_import_does_not_replace_real_runner() -> None:
    assert callable(run_experimentalist)
