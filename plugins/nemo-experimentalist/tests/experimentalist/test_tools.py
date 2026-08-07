# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import cast

from nemo_experimentalist_plugin.experimentalist.components.coder import Coder, CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import BLOCKED_MESSAGE
from nemo_experimentalist_plugin.experimentalist.components.tools import GuardedShellTools
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients, ConfiguredModelRefs, activate_model_clients
from nooa.agentdoc import pformat
from nooa.tools import ShellResult
from nooa.unifiedllm import CompletionClient, FakeLLMClient


async def test_guarded_shell_tools_runs_allowed_commands(tmp_path):
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run("python -", stdin="print('allowed')")
    finally:
        await shell.close()

    assert result.stdout.strip() == "allowed"
    assert result.returncode == 0
    assert result.success


async def test_guarded_shell_tools_returns_failure_for_blocked_paths(tmp_path):
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run("cat dataset/validation/secret")
    finally:
        await shell.close()

    assert isinstance(result, ShellResult)
    assert result.stdout == ""
    assert result.stderr == BLOCKED_MESSAGE
    assert result.returncode == 1
    assert not result.success


def test_coder_hides_skill_registry_that_can_replace_guarded_shell(tmp_path):
    nooa_skill = Path(__file__).resolve().parents[2] / "framework-skills" / "nooa"
    coder = Coder(workspace=tmp_path, framework_skills_dirs=[nooa_skill])

    rendered = pformat(coder)

    assert "skills=SkillRegistry" not in rendered
    assert "shell=ShellTools" in rendered
    assert "nooa=Nooa" in rendered


def test_coder_uses_default_model_for_architecture_docs(tmp_path: Path) -> None:
    default = cast(CompletionClient, FakeLLMClient())
    fast = cast(CompletionClient, FakeLLMClient())
    clients = ConfiguredModelClients(
        default=default,
        fast=fast,
        refs=ConfiguredModelRefs(default="default/quality", fast="default/fast"),
    )

    with activate_model_clients(clients):
        coder = Coder(workspace=tmp_path)

    assert coder._architecture_model is default


async def test_coder_lists_agent_mutation_models_from_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "models.yaml"
    catalog.write_text(
        """\
default_endpoint: https://models.example/v1
default_api_key_env: EXAMPLE_API_KEY
id_field: model_id
models:
  - model_id: provider/quality
    provider: Example
    range: quality
    notes: Quality model.
  - model_id: provider/fast
    provider: Example
    range: fast
    notes: Fast model.
""",
        encoding="utf-8",
    )
    coder = Coder(workspace=tmp_path, config=CoderConfig(model_catalog_path=catalog))

    assert await coder.list_available_models() == ["provider/quality", "provider/fast"]
