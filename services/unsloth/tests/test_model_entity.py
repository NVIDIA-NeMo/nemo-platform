# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the unsloth model_entity runner.

Covers:
- Adapter (LoRA) creation
- Full / merged model entity creation
- Update-on-conflict semantics (matches automodel behavior)
- Deployment launch with string-ref and inline DeploymentParameters
- Skipping deployment when there's already an active one for a LoRA base
- sanitize_name utility
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_job_ctx(workspace: str = "default"):
    from nmp.customization_common.service.context import NMPJobContext

    return NMPJobContext(
        workspace=workspace,
        job_id="job-1",
        attempt_id="attempt-0",
        step="model-entity-creation",
        task="task-1",
        jobs_url=None,
        files_url=None,
        storage_path=Path("/tmp"),
        config_path=Path("/tmp/cfg.json"),
    )


def _make_runner(sdk):
    from nmp.unsloth.tasks.model_entity.run import ModelEntityRunner

    return ModelEntityRunner(sdk=sdk, job_ctx=_make_job_ctx())


def _make_sdk() -> MagicMock:
    sdk = MagicMock()
    sdk.with_options.return_value = sdk
    return sdk


def _raise_runner_conflict() -> None:
    """Raise the ``ConflictError`` class the runner is bound against.

    See test_file_io.py for the rationale; same trick applies here because
    ``tasks/model_entity/__init__.py`` re-exports ``run`` as a function and
    shadows the submodule for plain attribute access.
    """
    import sys

    run_mod = sys.modules["nmp.unsloth.tasks.model_entity.run"]
    raise run_mod.ConflictError.__new__(run_mod.ConflictError, "already exists")


def _model_entity(*, workspace: str = "default", name: str = "base", spec: object | None = None) -> MagicMock:
    me = MagicMock()
    me.workspace = workspace
    me.name = name
    me.trust_remote_code = False
    me.spec = spec
    return me


# ---------------------------------------------------------------------------
# sanitize_name
# ---------------------------------------------------------------------------


class TestSanitizeName:
    def test_lowercases_and_replaces_invalid_chars(self) -> None:
        from nmp.unsloth.tasks.model_entity.run import sanitize_name

        assert sanitize_name("sft-cfg", "Qwen/Qwen3-0.6B") == "sft-cfg-qwen-qwen3-0.6b"

    def test_collapses_consecutive_hyphens(self) -> None:
        from nmp.unsloth.tasks.model_entity.run import sanitize_name

        # "/" is not in the allowed set, so each "/" becomes "-", then
        # the consecutive-hyphen collapse fires.
        assert sanitize_name("p", "a//b") == "p-a-b"

    def test_caps_length_below_60_and_strips_trailing_hyphen(self) -> None:
        from nmp.unsloth.tasks.model_entity.run import sanitize_name

        # 59-char limit accounts for the "-v1" the backend appends.
        long_name = "a" * 80
        result = sanitize_name("sft-deploy", long_name)
        assert len(result) <= 59
        assert not result.endswith("-")


# ---------------------------------------------------------------------------
# ModelEntityRunner.create_model_entity — full / merged path
# ---------------------------------------------------------------------------


class TestCreateFullEntity:
    def test_creates_model_entity_for_full_sft(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig

        sdk = _make_sdk()
        sdk.models.retrieve.return_value = _model_entity(name="base-model")
        new_me = _model_entity(name="trained-model")
        sdk.models.create.return_value = new_me

        runner = _make_runner(sdk)
        config = ModelEntityTaskConfig(
            name="trained-model",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="trained-model"),
            model_entity="default/base-model",
            peft=None,
        )

        result, deploy_target = runner.create_model_entity(config)

        sdk.files.filesets.retrieve.assert_called_once_with(workspace="default", name="trained-model")
        sdk.models.create.assert_called_once()
        assert deploy_target is new_me
        # ``result`` is the output of ``new_me.model_dump()`` — we just assert
        # we got *something* back; the actual shape is controlled by the SDK.
        assert result is not None

    def test_conflict_falls_back_to_update(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig

        sdk = _make_sdk()
        sdk.models.retrieve.return_value = _model_entity(name="base-model")
        sdk.models.create.side_effect = lambda **_: _raise_runner_conflict()
        sdk.models.update.return_value = _model_entity(name="trained-model")

        runner = _make_runner(sdk)
        config = ModelEntityTaskConfig(
            name="trained-model",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="trained-model"),
            model_entity="default/base-model",
            peft=None,
        )

        _, _ = runner.create_model_entity(config)

        sdk.models.update.assert_called_once()
        update_call = sdk.models.update.call_args
        assert update_call.kwargs["name"] == "trained-model"
        assert update_call.kwargs["workspace"] == "default"

    def test_missing_fileset_raises_creation_error(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityCreationError, ModelEntityTaskConfig

        sdk = _make_sdk()
        sdk.files.filesets.retrieve.side_effect = RuntimeError("fileset missing")
        runner = _make_runner(sdk)
        config = ModelEntityTaskConfig(
            name="x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="missing"),
            model_entity="default/base-model",
        )

        with pytest.raises(ModelEntityCreationError, match="does not exist or is not accessible"):
            runner.create_model_entity(config)


# ---------------------------------------------------------------------------
# ModelEntityRunner.create_model_entity — LoRA adapter path
# ---------------------------------------------------------------------------


class TestCreateAdapter:
    def test_creates_adapter_for_lora(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig, PEFTConfig
        from nmp.unsloth.entities.values import FinetuningType

        sdk = _make_sdk()
        base_me = _model_entity(name="base-model")
        sdk.models.retrieve.return_value = base_me
        sdk.models.adapters.create.return_value = _model_entity(name="adapter-x")

        runner = _make_runner(sdk)
        config = ModelEntityTaskConfig(
            name="adapter-x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="adapter-x"),
            model_entity="default/base-model",
            peft=PEFTConfig(type=FinetuningType.LORA, rank=8, alpha=16),
        )

        _result, deploy_target = runner.create_model_entity(config)

        sdk.models.adapters.create.assert_called_once()
        # For LoRA, the deploy target is the BASE model, not the adapter.
        assert deploy_target is base_me

    def test_adapter_conflict_falls_back_to_update(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig, PEFTConfig
        from nmp.unsloth.entities.values import FinetuningType

        sdk = _make_sdk()
        sdk.models.retrieve.return_value = _model_entity(name="base-model")
        sdk.models.adapters.create.side_effect = lambda **_: _raise_runner_conflict()
        sdk.models.adapters.update.return_value = _model_entity(name="adapter-x")

        runner = _make_runner(sdk)
        config = ModelEntityTaskConfig(
            name="adapter-x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="adapter-x"),
            model_entity="default/base-model",
            peft=PEFTConfig(type=FinetuningType.LORA, rank=8, alpha=16),
        )

        runner.create_model_entity(config)

        sdk.models.adapters.update.assert_called_once()


# ---------------------------------------------------------------------------
# ModelEntityRunner.launch_model
# ---------------------------------------------------------------------------


class TestLaunchModel:
    def test_no_deployment_config_returns_early(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig

        sdk = _make_sdk()
        runner = _make_runner(sdk)
        me = _model_entity(name="x")
        config = ModelEntityTaskConfig(
            name="x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="x"),
            model_entity="default/base",
            deployment_config=None,
        )

        runner.launch_model(config, me)

        sdk.inference.deployments.create.assert_not_called()
        sdk.inference.deployment_configs.create.assert_not_called()

    def test_inline_params_creates_config_then_deployment(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import DeploymentParameters, ModelEntityTaskConfig

        sdk = _make_sdk()
        sdk.inference.deployment_configs.create.return_value = types.SimpleNamespace(
            workspace="default",
            name="sft-cfg-x",
        )
        sdk.inference.deployments.create.return_value = types.SimpleNamespace(
            workspace="default",
            name="sft-deploy-x",
        )
        sdk.inference.deployments.retrieve.return_value = types.SimpleNamespace(
            workspace="default",
            name="sft-deploy-x",
            status="PENDING",
        )

        runner = _make_runner(sdk)
        me = _model_entity(name="x", spec=types.SimpleNamespace(family="llama", base_num_parameters=1_000_000_000))
        config = ModelEntityTaskConfig(
            name="x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="x"),
            model_entity="default/base",
            deployment_config=DeploymentParameters(gpu=1, image_name="img", image_tag="1.0"),
        )

        runner.launch_model(config, me)

        sdk.inference.deployment_configs.create.assert_called_once()
        sdk.inference.deployments.create.assert_called_once()

    def test_string_ref_resolves_existing_config(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig

        sdk = _make_sdk()
        sdk.inference.deployment_configs.retrieve.return_value = types.SimpleNamespace(
            workspace="default",
            name="existing-cfg",
        )
        sdk.inference.deployments.create.return_value = types.SimpleNamespace(
            workspace="default",
            name="sft-deploy-x",
        )
        sdk.inference.deployments.retrieve.return_value = types.SimpleNamespace(
            workspace="default",
            name="sft-deploy-x",
            status="PENDING",
        )

        runner = _make_runner(sdk)
        me = _model_entity(name="x", spec=types.SimpleNamespace(family="llama", base_num_parameters=1))
        config = ModelEntityTaskConfig(
            name="x",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="x"),
            model_entity="default/base",
            deployment_config="existing-cfg",
        )

        runner.launch_model(config, me)

        sdk.inference.deployment_configs.retrieve.assert_called_once_with(
            workspace="default",
            name="existing-cfg",
        )
        sdk.inference.deployment_configs.create.assert_not_called()
        sdk.inference.deployments.create.assert_called_once()

    def test_lora_with_active_deployment_skips(self) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import (
            DeploymentParameters,
            ModelEntityTaskConfig,
            PEFTConfig,
        )
        from nmp.unsloth.entities.values import FinetuningType

        sdk = _make_sdk()
        # Active deployment exists → launch_model should return without creating anything.
        existing_config = types.SimpleNamespace(workspace="default", name="cfg-1")
        active_deployment = types.SimpleNamespace(status="READY")
        sdk.inference.deployment_configs.list.return_value = types.SimpleNamespace(data=[existing_config])
        sdk.inference.deployments.list.return_value = types.SimpleNamespace(data=[active_deployment])

        runner = _make_runner(sdk)
        me = _model_entity(name="base")
        config = ModelEntityTaskConfig(
            name="adapter",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="adapter"),
            model_entity="default/base",
            peft=PEFTConfig(type=FinetuningType.LORA, rank=8, alpha=16),
            deployment_config=DeploymentParameters(),
        )

        runner.launch_model(config, me)

        sdk.inference.deployment_configs.create.assert_not_called()
        sdk.inference.deployments.create.assert_not_called()

    def test_lora_with_lora_enabled_false_warns_and_skips(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef
        from nmp.customization_common.schemas.model_entity import (
            DeploymentParameters,
            ModelEntityTaskConfig,
            PEFTConfig,
        )
        from nmp.unsloth.entities.values import FinetuningType

        sdk = _make_sdk()
        sdk.inference.deployment_configs.list.return_value = types.SimpleNamespace(data=[])

        runner = _make_runner(sdk)
        me = _model_entity(name="base")
        config = ModelEntityTaskConfig(
            name="adapter",
            workspace="default",
            fileset=FileSetRef(workspace="default", name="adapter"),
            model_entity="default/base",
            peft=PEFTConfig(type=FinetuningType.LORA, rank=8, alpha=16),
            deployment_config=DeploymentParameters(lora_enabled=False),
        )

        with caplog.at_level("WARNING"):
            runner.launch_model(config, me)

        assert any("lora_enabled is false" in r.getMessage() for r in caplog.records)
        sdk.inference.deployments.create.assert_not_called()


# ---------------------------------------------------------------------------
# Compiler → deployment_config plumbing
# ---------------------------------------------------------------------------


class TestCompilerDeploymentConfigPlumbing:
    @pytest.mark.asyncio
    async def test_inline_params_pass_through_to_model_entity_step(self) -> None:
        from unittest.mock import AsyncMock

        from nmp.unsloth.app.jobs.compiler import platform_job_config_compiler
        from nmp.unsloth.schemas import (
            DatasetSpec,
            DeploymentParams,
            LoRAParams,
            ModelLoadSpec,
            OutputResponse,
            ScheduleSpec,
            TrainingSpec,
            UnslothJobOutput,
        )

        spec = UnslothJobOutput(
            model=ModelLoadSpec(name="default/base"),
            dataset=DatasetSpec(path="default/training"),
            training=TrainingSpec(lora=LoRAParams()),
            schedule=ScheduleSpec(max_steps=1),
            output=OutputResponse(name="r", type="adapter", save_method="lora", fileset="r"),
            deployment_config=DeploymentParams(gpu=2, image_name="img", lora_enabled=True),
        )

        # Patch fetch_model_entity to avoid hitting the platform.
        from nmp.unsloth.app.jobs import compiler as compiler_mod

        original_fetch = compiler_mod.fetch_model_entity
        compiler_mod.fetch_model_entity = AsyncMock(
            return_value=types.SimpleNamespace(
                workspace="default",
                name="base",
                fileset="default/base-fileset",
                trust_remote_code=False,
            )
        )
        try:
            job_spec = await platform_job_config_compiler(
                workspace="default",
                job_spec=spec,
                sdk=MagicMock(),
            )
        finally:
            compiler_mod.fetch_model_entity = original_fetch

        # PlatformJobSpec is a TypedDict, so we index it instead of using attributes.
        me_step = next(s for s in job_spec["steps"] if s["name"] == "model-entity-creation")
        dc = me_step["config"]["deployment_config"]
        # Inline params come through as a serialized dict, not the user-facing class.
        assert dc["gpu"] == 2
        assert dc["image_name"] == "img"
        assert dc["lora_enabled"] is True

    @pytest.mark.asyncio
    async def test_string_ref_passes_through_unchanged(self) -> None:
        from unittest.mock import AsyncMock

        from nmp.unsloth.app.jobs.compiler import platform_job_config_compiler
        from nmp.unsloth.schemas import (
            DatasetSpec,
            LoRAParams,
            ModelLoadSpec,
            OutputResponse,
            ScheduleSpec,
            TrainingSpec,
            UnslothJobOutput,
        )

        spec = UnslothJobOutput(
            model=ModelLoadSpec(name="default/base"),
            dataset=DatasetSpec(path="default/training"),
            training=TrainingSpec(lora=LoRAParams()),
            schedule=ScheduleSpec(max_steps=1),
            output=OutputResponse(name="r", type="adapter", save_method="lora", fileset="r"),
            deployment_config="my-config",
        )

        from nmp.unsloth.app.jobs import compiler as compiler_mod

        original_fetch = compiler_mod.fetch_model_entity
        compiler_mod.fetch_model_entity = AsyncMock(
            return_value=types.SimpleNamespace(
                workspace="default",
                name="base",
                fileset="default/base-fileset",
                trust_remote_code=False,
            )
        )
        try:
            job_spec = await platform_job_config_compiler(
                workspace="default",
                job_spec=spec,
                sdk=MagicMock(),
            )
        finally:
            compiler_mod.fetch_model_entity = original_fetch

        me_step = next(s for s in job_spec["steps"] if s["name"] == "model-entity-creation")
        assert me_step["config"]["deployment_config"] == "my-config"
