# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_optimization.schemas.optimize import OptimizeSpec
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nemo_platform_plugin.run_dependencies import LocalRunError
from pydantic import ValidationError

FABRIC_AGENT = {
    "schema_version": "fabric.agent/v1alpha1",
    "metadata": {"name": "hermes-optimize-demo"},
}


@pytest.mark.asyncio
async def test_compile_produces_customization_optimize_task() -> None:
    spec = OptimizeSpec(optimize_config="/abs/optimize.yml")
    platform_spec = await OptimizeJob.compile(
        workspace="staging",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    step = next(iter(platform_spec["steps"]))
    assert step["name"] == "optimize"
    executor = step["executor"]
    assert executor.get("provider") == "subprocess"
    assert executor.get("command") == ["python", "-m", "nemo_optimization.tasks.optimize"]
    assert step["config"]["workspace"] == "staging"


@pytest.mark.asyncio
async def test_compile_rejects_relative_optimize_config() -> None:
    spec = OptimizeSpec(optimize_config="./relative.yml")
    with pytest.raises(PlatformJobCompilationError, match="optimize_config must be an absolute path"):
        await OptimizeJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


def test_run_dispatches_inline_fabric_config(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "fabric.agent/v1alpha1",
                "metadata": {"name": "inline"},
                "optimizer": {"numeric": {"enabled": True}},
            }
        )
    )

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        result = OptimizeJob().run(
            {"optimize_config": str(optimize_yaml), "workspace": "default"},
            ctx=ctx,
        )

    assert result["status"] == "completed"
    kwargs = dispatch.call_args.kwargs
    assert kwargs["agent_config"] is None
    assert kwargs["optimize_config"]["optimizer"]["numeric"]["enabled"] is True


def test_run_resolves_platform_agent_before_dispatch(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text("optimizer:\n  numeric:\n    enabled: true\n")

    platform_agent = {
        "config_format": "nemo-agents-spec-v1",
        "name": "react-agent",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
                "model": {
                    "provider": "openai",
                    "model": "demo-model",
                    "base_url": "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
                    "api_key_env": "NEMO_AGENTS_IGW_API_KEY",
                },
                "settings": {"max_tokens": 256, "reasoning_config": {"effort": "none"}},
            }
        },
        "instructions": {"system": {"content": "Be brief."}},
        "environment": {"provider": "local", "workspace": "./workspace", "artifacts": "./artifacts"},
        "models": {
            "judge": {
                "provider": "openai",
                "model": "demo-model",
                "base_url": "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
                "api_key_env": "NEMO_AGENTS_IGW_API_KEY",
            }
        },
    }

    class _StubAgents:
        def get(self, *, name: str, workspace: str) -> dict[str, Any]:
            assert name == "react-agent"
            assert workspace == "default"
            return {"config": platform_agent}

    class _StubSDK:
        agents = _StubAgents()

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(
            {
                "optimize_config": str(optimize_yaml),
                "workspace": "default",
                "agent": "react-agent",
            },
            ctx=ctx,
            sdk=cast(NeMoPlatform, _StubSDK()),
        )

    agent_config = dispatch.call_args.kwargs["agent_config"]
    assert agent_config["schema_version"] == "fabric.agent/v1alpha1"
    assert agent_config["harness"]["adapter_id"] == "nvidia.fabric.hermes"
    assert agent_config["models"]["default"]["model"] == "demo-model"
    assert agent_config["models"]["judge"]["model"] == "demo-model"


@pytest.mark.asyncio
async def test_compile_accepts_inline_optimize_config() -> None:
    spec = OptimizeSpec(optimize_config_inline={"optimizer": {"numeric": {"enabled": True}}})
    platform_spec = await OptimizeJob.compile(
        workspace="staging",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    step = next(iter(platform_spec["steps"]))
    assert step["config"]["optimize_config_inline"] == {"optimizer": {"numeric": {"enabled": True}}}


def test_run_accepts_inline_optimize_config(ctx: JobContext) -> None:
    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        result = OptimizeJob().run(
            {
                "optimize_config_inline": {"optimizer": {"numeric": {"enabled": True, "n_trials": 8}}},
                "workspace": "default",
            },
            ctx=ctx,
        )

    assert result["status"] == "completed"
    assert dispatch.call_args.kwargs["optimize_config"]["optimizer"]["numeric"]["n_trials"] == 8


def test_run_expands_env_vars_in_inline_config(ctx: JobContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPTIMIZE_TEST_MODEL", "demo-model")

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(
            {
                "optimize_config_inline": {"models": {"default": {"model": "${OPTIMIZE_TEST_MODEL}"}}},
                "workspace": "default",
            },
            ctx=ctx,
        )

    assert dispatch.call_args.kwargs["optimize_config"]["models"]["default"]["model"] == "demo-model"


def test_spec_requires_exactly_one_config_source() -> None:
    with pytest.raises(ValidationError, match="got neither"):
        OptimizeSpec()
    with pytest.raises(ValidationError, match="got both"):
        OptimizeSpec(optimize_config="/abs/optimize.yml", optimize_config_inline={"optimizer": {}})


def _inline_config_with_dataset(dataset: Any) -> dict[str, Any]:
    return {
        "optimizer": {"numeric": {"enabled": True}},
        "eval": {"general": {"dataset": dataset, "max_concurrency": 1}},
    }


def test_run_stages_dataset_from_fileset_ref(ctx: JobContext) -> None:
    downloaded: dict[str, Any] = {}

    class _StubFiles:
        def download(self, *, local_path: str, fileset: str, workspace: str) -> None:
            downloaded.update(fileset=fileset, workspace=workspace)
            (Path(local_path) / "rows.json").write_text('[{"question": "q", "answer": "a"}]')

    class _StubSDK:
        files = _StubFiles()

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(
            {
                "optimize_config_inline": _inline_config_with_dataset({"file_path": "default/evals#rows.json"}),
                "workspace": "default",
            },
            ctx=ctx,
            sdk=cast(NeMoPlatform, _StubSDK()),
        )

    assert downloaded == {"fileset": "evals", "workspace": "default"}
    staged = dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["dataset"]["file_path"]
    assert staged.endswith("rows.json")
    assert Path(staged).is_absolute()
    # Sibling keys survive the rewrite.
    assert dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["max_concurrency"] == 1


def test_run_leaves_plain_dataset_path_untouched(ctx: JobContext) -> None:
    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(
            {
                "optimize_config_inline": _inline_config_with_dataset({"file_path": "/data/rows.json"}),
                "workspace": "default",
            },
            ctx=ctx,
        )

    dataset = dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["dataset"]
    assert dataset == {"file_path": "/data/rows.json"}


INLINE_MINIMAL = {"optimizer": {"numeric": {"enabled": True}}}


def _write_study_artifacts(ctx: JobContext) -> Path:
    """Stand in for what a backend leaves behind under <persistent>/results."""
    artifacts = ctx.storage.persistent / "results" / "optimizer_results"
    artifacts.mkdir(parents=True)
    (artifacts / "study_summary.json").write_text('{"status": "completed"}')
    (artifacts / "optimized_config.yml").write_text("optimizer: {}\n")
    return artifacts


def test_run_publishes_results_to_fileset(ctx: JobContext) -> None:
    uploaded: dict[str, Any] = {}

    class _StubFiles:
        def upload(self, *, local_path: str, fileset: str, workspace: str, fileset_auto_create: bool) -> Any:
            uploaded.update(
                local_path=local_path,
                fileset=fileset,
                workspace=workspace,
                auto_create=fileset_auto_create,
                names=sorted(p.name for p in Path(local_path).rglob("*") if p.is_file()),
            )
            return SimpleNamespace(name=fileset)

    class _StubSDK:
        files = _StubFiles()

    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        _write_study_artifacts(ctx)
        return {"status": "completed", "best_trial": 3}

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch):
        result = OptimizeJob().run(
            {"optimize_config_inline": INLINE_MINIMAL, "workspace": "default", "output": "tuned-results"},
            ctx=ctx,
            sdk=cast(NeMoPlatform, _StubSDK()),
        )

    assert uploaded["fileset"] == "tuned-results"
    assert uploaded["workspace"] == "default"
    assert uploaded["auto_create"] is True
    # Trailing slash uploads contents, not the dir itself.
    assert uploaded["local_path"].endswith("/")
    assert uploaded["names"] == ["optimized_config.yml", "study_summary.json"]
    # The study's own summary survives alongside the new pointer.
    assert result["best_trial"] == 3
    assert result["output"] == {"type": "fileset", "fileset": "default/tuned-results"}


def test_run_publishes_results_to_local_dir(ctx: JobContext, tmp_path: Path) -> None:
    dest = tmp_path / "published"

    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        _write_study_artifacts(ctx)
        return {"status": "completed"}

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch):
        result = OptimizeJob().run(
            {"optimize_config_inline": INLINE_MINIMAL, "workspace": "default", "output": str(dest)},
            ctx=ctx,
        )

    assert (dest / "optimizer_results" / "study_summary.json").is_file()
    assert result["output"] == {"type": "local_dir", "path": str(dest.resolve())}


def test_run_without_output_publishes_nothing(ctx: JobContext) -> None:
    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        _write_study_artifacts(ctx)
        return {"status": "completed"}

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch):
        result = OptimizeJob().run(
            {"optimize_config_inline": INLINE_MINIMAL, "workspace": "default"},
            ctx=ctx,
        )

    assert result == {"status": "completed"}


def test_run_does_not_publish_when_study_fails(ctx: JobContext) -> None:
    """A crashed study must not leave partial artifacts in the target fileset."""

    class _StubFiles:
        def upload(self, **kwargs: Any) -> Any:
            raise AssertionError("upload must not run when the study raises")

    class _StubSDK:
        files = _StubFiles()

    with (
        patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=RuntimeError("study blew up")),
        pytest.raises(RuntimeError, match="study blew up"),
    ):
        OptimizeJob().run(
            {"optimize_config_inline": INLINE_MINIMAL, "workspace": "default", "output": "tuned-results"},
            ctx=ctx,
            sdk=cast(NeMoPlatform, _StubSDK()),
        )


def test_run_rejects_fileset_output_without_sdk(ctx: JobContext) -> None:
    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        _write_study_artifacts(ctx)
        return {"status": "completed"}

    with (
        patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch),
        pytest.raises(LocalRunError, match="requires a 'sdk: NeMoPlatform'"),
    ):
        OptimizeJob().run(
            {"optimize_config_inline": INLINE_MINIMAL, "workspace": "default", "output": "tuned-results"},
            ctx=ctx,
        )


def test_run_reports_missing_artifacts_on_publish(ctx: JobContext, tmp_path: Path) -> None:
    """A backend that claims success but writes nothing is a bug, not an empty upload."""
    with (
        patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}),
        pytest.raises(FileNotFoundError, match="wrote no artifacts"),
    ):
        OptimizeJob().run(
            {
                "optimize_config_inline": INLINE_MINIMAL,
                "workspace": "default",
                "output": str(tmp_path / "published"),
            },
            ctx=ctx,
        )


def test_run_rejects_endpoint_agent(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text("optimizer:\n  numeric:\n    enabled: true\n")

    with pytest.raises(LocalRunError, match="Endpoint URL / URI optimize mode has been removed"):
        OptimizeJob().run(
            {
                "optimize_config": str(optimize_yaml),
                "workspace": "default",
                "agent": "http://localhost:8080",
            },
            ctx=ctx,
        )
