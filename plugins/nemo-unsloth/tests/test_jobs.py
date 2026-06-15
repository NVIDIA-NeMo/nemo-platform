# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for UnslothJob lifecycle (to_spec + compile).

After the 2026 migration from local run to container submit we no longer
exercise ``train_sft`` from these tests — that lives in the
``nmp-unsloth-training`` container's smoke test. Here we just pin:

- ``to_spec`` resolves output naming + fileset against a stub SDK.
- ``compile`` delegates to the service-side compiler (we patch it out)
  and returns the resulting ``PlatformJobSpec`` after the Docker
  runtime check.
- The Docker runtime check fires when the platform isn't configured for
  Docker.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nemo_unsloth_plugin.jobs.jobs import UnslothJob
from nemo_unsloth_plugin.schema import UnslothJobInput
from nmp.unsloth.schemas import UnslothJobOutput


def _input_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": {"name": "default/base"},
        "dataset": {"path": "default/training"},
        "schedule": {"max_steps": 60},
    }
    base.update(overrides)
    return base


def _stub_async_sdk() -> SimpleNamespace:
    """Async SDK used by ``to_spec`` (validates refs)."""
    me = SimpleNamespace(
        name="base",
        workspace="default",
        spec=None,
        fileset="base-fs",
        trust_remote_code=False,
    )
    return SimpleNamespace(
        models=SimpleNamespace(retrieve=AsyncMock(return_value=me)),
        files=SimpleNamespace(
            filesets=SimpleNamespace(retrieve=AsyncMock(return_value=SimpleNamespace())),
        ),
    )


def _make_canonical(workspace: str = "default", **overrides: Any) -> UnslothJobOutput:
    spec = UnslothJobInput.model_validate(_input_dict(**overrides))
    return asyncio.run(
        UnslothJob.to_spec(
            spec,
            workspace=workspace,
            entity_client=object(),
            async_sdk=_stub_async_sdk(),
            is_local=False,
        ),
    )


class TestToSpec:
    def test_to_spec_resolves_output(self) -> None:
        out = _make_canonical()
        assert isinstance(out, UnslothJobOutput)
        assert out.output.type == "adapter"
        assert out.output.save_method == "lora"
        # Fileset defaults to the entity name (mirrors automodel).
        assert out.output.fileset == out.output.name


class TestCompile:
    def test_compile_delegates_to_service_compiler(self) -> None:
        """When the runtime check passes, ``compile`` returns whatever the service builds."""
        canonical = _make_canonical()
        fake_spec = SimpleNamespace(
            steps=["model-and-dataset-download", "training", "model-upload", "model-entity-creation"]
        )

        with (
            patch("nemo_unsloth_plugin.jobs.jobs.require_docker_runtime"),
            patch(
                "nemo_unsloth_plugin.jobs.jobs.platform_job_config_compiler",
                new=AsyncMock(return_value=fake_spec),
            ) as compile_mock,
            patch(
                "nemo_unsloth_plugin.jobs.jobs.validate_gpu_available_for_docker",
                new=MagicMock(),
            ) as validate_mock,
        ):
            result = asyncio.run(
                UnslothJob.compile(
                    workspace="default",
                    spec=canonical,
                    entity_client=object(),
                    job_name="my-unsloth-job",
                    async_sdk=object(),
                    profile=None,
                ),
            )

        assert result is fake_spec
        compile_mock.assert_awaited_once()
        validate_mock.assert_called_once_with(fake_spec)
        kwargs = compile_mock.await_args.kwargs
        assert kwargs["workspace"] == "default"
        assert kwargs["job_name"] == "my-unsloth-job"
        # Profile falls through to the unsloth config default (`gpu`).
        assert kwargs["profile"] == "gpu"

    def test_compile_passes_caller_profile_override(self) -> None:
        canonical = _make_canonical()
        with (
            patch("nemo_unsloth_plugin.jobs.jobs.require_docker_runtime"),
            patch(
                "nemo_unsloth_plugin.jobs.jobs.platform_job_config_compiler",
                new=AsyncMock(return_value=SimpleNamespace(steps=[])),
            ) as compile_mock,
            patch("nemo_unsloth_plugin.jobs.jobs.validate_gpu_available_for_docker"),
        ):
            asyncio.run(
                UnslothJob.compile(
                    workspace="default",
                    spec=canonical,
                    entity_client=object(),
                    job_name=None,
                    async_sdk=object(),
                    profile="gpu_distributed",
                ),
            )

        assert compile_mock.await_args.kwargs["profile"] == "gpu_distributed"

    def test_compile_rejects_non_docker_runtime(self) -> None:
        canonical = _make_canonical()
        # Force the runtime check to raise so we don't need a Docker daemon
        # in CI. The check is what runs first; the rest never executes.
        with patch(
            "nemo_unsloth_plugin.jobs.jobs.require_docker_runtime",
            side_effect=PlatformJobCompilationError("not docker"),
        ):
            with pytest.raises(PlatformJobCompilationError, match="not docker"):
                asyncio.run(
                    UnslothJob.compile(
                        workspace="default",
                        spec=canonical,
                        entity_client=object(),
                        job_name=None,
                        async_sdk=object(),
                    ),
                )


class TestNoRun:
    def test_unsloth_job_is_abstract_because_run_is_not_implemented(self) -> None:
        """``NemoJob.run`` is ``@abstractmethod`` and we deliberately don't override it.

        Pin so a future override doesn't silently re-enable local run —
        Unsloth migrated to container submit in 2026. ``run`` lives in
        the ``nmp-unsloth-training`` container's ``__main__`` now.
        """
        with pytest.raises(TypeError, match="abstract"):
            UnslothJob()
