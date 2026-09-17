# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``AgentOptimizeJob.run``/``compile`` are unimplemented stubs; strategies write their own,
optionally using the shared helpers below (``split_agent_ref``, ``fetch_agent_config``,
``_staged_bundle``, ``_bundle_workdir``, ``_load_yaml``), which these tests exercise directly."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, ClassVar

import pytest
from nemo_agent_optimization_plugin import job_base
from nemo_agent_optimization_plugin.job_base import AgentOptimizeJob, fetch_agent_config, split_agent_ref
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.run_dependencies import LocalRunError


@pytest.fixture
def ctx(tmp_path: Path) -> JobContext:
    ephemeral = tmp_path / "ephemeral"
    persistent = tmp_path / "persistent"
    ephemeral.mkdir()
    persistent.mkdir()
    return JobContext(
        workspace="my-ws",
        storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
        results=LocalJobResults(root=persistent / "results"),
    )


SOURCE = {
    "config_format": "nemo-agents-spec-v1",
    "name": "my-agent",
    "default_harness": "hermes",
    "harnesses": {"hermes": {"kind": "hermes", "model": {"provider": "openai", "model": "m"}}},
}


class _Bare(AgentOptimizeJob):
    name: ClassVar[str] = "agent_optimize"
    strategy: ClassVar[str] = "bare"


def test_the_base_class_run_is_an_unimplemented_stub(ctx: JobContext) -> None:
    with pytest.raises(NotImplementedError, match="must override run"):
        _Bare().run({}, ctx=ctx, sdk=object())


def test_the_base_class_compile_is_an_unimplemented_stub() -> None:
    with pytest.raises(NotImplementedError, match="must override compile"):
        asyncio.run(
            _Bare.compile(
                workspace="my-ws",
                spec=None,
                entity_client=None,
                job_name=None,
                async_sdk=None,
            )
        )


def test_split_agent_ref_uses_the_workspace_prefix_when_present() -> None:
    assert split_agent_ref("other-ws/my-agent", workspace="my-ws") == ("other-ws", "my-agent")


def test_split_agent_ref_defaults_to_the_run_workspace() -> None:
    assert split_agent_ref("my-agent", workspace="my-ws") == ("my-ws", "my-agent")


def test_fetch_agent_config_returns_the_stored_config() -> None:
    class _Sdk:
        class agents:  # noqa: N801 - matches the SDK's own accessor shape
            @staticmethod
            def get(name: str, *, workspace: str) -> dict[str, Any]:
                assert (workspace, name) == ("my-ws", "my-agent")
                return {"config": SOURCE}

    assert fetch_agent_config("my-ws/my-agent", workspace="my-ws", sdk=_Sdk()) == SOURCE


def test_fetch_agent_config_rejects_an_empty_stored_config() -> None:
    class _Sdk:
        class agents:  # noqa: N801 - matches the SDK's own accessor shape
            @staticmethod
            def get(name: str, *, workspace: str) -> dict[str, Any]:
                return {"config": {}}

    with pytest.raises(LocalRunError, match="empty or invalid"):
        fetch_agent_config("my-ws/my-agent", workspace="my-ws", sdk=_Sdk())


def test_load_yaml_expands_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_VAR", "expanded")
    config_path = tmp_path / "optimize.yaml"
    config_path.write_text('tuning: {a: 1, b: "${SOME_VAR}"}\n', encoding="utf-8")

    assert job_base._load_yaml(config_path) == {"tuning": {"a": 1, "b": "expanded"}}


def test_load_yaml_rejects_a_non_mapping_document(tmp_path: Path) -> None:
    config_path = tmp_path / "optimize.yaml"
    config_path.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        job_base._load_yaml(config_path)


def test_bundle_workdir_chdirs_for_the_duration_of_the_block(tmp_path: Path) -> None:
    before = Path.cwd()
    with job_base._bundle_workdir(tmp_path):
        assert Path.cwd() == tmp_path.resolve()
    assert Path.cwd() == before


def test_staged_bundle_yields_the_config_path_and_bundle_root(
    tmp_path: Path, ctx: JobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    (bundle / "configs").mkdir(parents=True)
    config_path = bundle / "configs" / "optimize.yaml"
    config_path.write_text("tuning: {a: 1}\n", encoding="utf-8")

    @contextlib.contextmanager
    def fake_resolve_staged_config(*_args: Any, **_kwargs: Any):
        yield config_path

    monkeypatch.setattr(
        "nemo_agents_plugin.jobs.fileset_io.resolve_staged_config",
        fake_resolve_staged_config,
    )

    from nemo_agent_optimization_plugin.schemas.optimize import AgentOptimizeSpec

    spec = AgentOptimizeSpec.model_validate(
        {
            "agent": "my-ws/my-agent",
            "optimize_config_fileset": "my-ws/bundle",
            "optimize_config": "configs/optimize.yaml",
            "output_agent": "my-agent-opt",
            "workspace": "my-ws",
        }
    )

    with job_base._staged_bundle(spec, ctx=ctx, sdk=object()) as (yielded_path, bundle_root):
        assert yielded_path == config_path
        assert bundle_root == bundle
