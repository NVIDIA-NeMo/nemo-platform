# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nemo_customizer_plugin.backends._dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nemo_customizer_plugin.backends import _dispatch
from nemo_customizer_plugin.backends._dispatch import dispatch_in_process
from nemo_customizer_plugin.jobs.finetune import FinetuneSpec


def _fake_ctx(tmp_path: Path):
    """Build a minimal JobContext-shaped object good enough for dispatch tests."""
    from nemo_platform_plugin.job_context import JobContext, StoragePaths
    from nemo_platform_plugin.job_results import LocalJobResults

    ephemeral = tmp_path / "eph"
    persistent = tmp_path / "per"
    ephemeral.mkdir()
    persistent.mkdir()
    return JobContext(
        workspace="test",
        storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
        results=LocalJobResults(root=persistent / "results"),
        job_id=None,
    )


class TestDispatchInProcess:
    def test_sets_cuda_visible_devices_when_gpus_specified(self, tmp_path, monkeypatch):
        spec = FinetuneSpec(training_type="sft", backend="unsloth", gpus="0,1")
        ctx = _fake_ctx(tmp_path)

        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

        fake_backend = MagicMock()
        fake_backend.train_sft = MagicMock(return_value={"loss": 0.5})
        with patch.dict(
            "sys.modules",
            {"nemo_customizer_plugin.backends.unsloth": fake_backend},
        ):
            result = dispatch_in_process(spec, ctx)

        import os

        assert os.environ.get("CUDA_VISIBLE_DEVICES") == "0,1"
        assert result == {"loss": 0.5}
        fake_backend.train_sft.assert_called_once_with(spec, ctx)

    def test_does_not_set_cuda_visible_devices_when_gpus_none(self, tmp_path, monkeypatch):
        spec = FinetuneSpec(training_type="sft", backend="unsloth", gpus=None)
        ctx = _fake_ctx(tmp_path)

        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

        fake_backend = MagicMock()
        fake_backend.train_sft = MagicMock(return_value={"loss": 0.1})
        with patch.dict(
            "sys.modules",
            {"nemo_customizer_plugin.backends.unsloth": fake_backend},
        ):
            dispatch_in_process(spec, ctx)

        import os

        assert "CUDA_VISIBLE_DEVICES" not in os.environ

    def test_dispatches_to_unsloth_backend(self, tmp_path):
        spec = FinetuneSpec(training_type="sft", backend="unsloth")
        ctx = _fake_ctx(tmp_path)

        fake = MagicMock()
        fake.train_sft = MagicMock(return_value={"backend": "unsloth"})
        with patch.dict("sys.modules", {"nemo_customizer_plugin.backends.unsloth": fake}):
            result = dispatch_in_process(spec, ctx)

        assert result == {"backend": "unsloth"}

    def test_automodel_stub_raises(self, tmp_path):
        """The stub backend's NotImplementedError surfaces through dispatch."""
        spec = FinetuneSpec(training_type="sft", backend="automodel")
        ctx = _fake_ctx(tmp_path)
        with pytest.raises(NotImplementedError, match="services/customizer/"):
            dispatch_in_process(spec, ctx)

    def test_megatron_bridge_stub_raises(self, tmp_path):
        spec = FinetuneSpec(training_type="sft", backend="megatron-bridge")
        ctx = _fake_ctx(tmp_path)
        with pytest.raises(NotImplementedError, match="services/customizer/"):
            dispatch_in_process(spec, ctx)

    def test_unknown_backend_raises(self, tmp_path):
        spec = FinetuneSpec.model_construct(training_type="sft", backend="bogus", gpus=None)
        ctx = _fake_ctx(tmp_path)
        with pytest.raises(ValueError, match="Unknown backend"):
            dispatch_in_process(spec, ctx)

    def test_unsupported_training_type_raises(self, tmp_path):
        spec = FinetuneSpec.model_construct(training_type="dpo", backend="unsloth", gpus=None)
        ctx = _fake_ctx(tmp_path)

        fake = MagicMock()
        with patch.dict("sys.modules", {"nemo_customizer_plugin.backends.unsloth": fake}):
            with pytest.raises(ValueError, match="Unsupported training_type"):
                dispatch_in_process(spec, ctx)


# ``_dispatch`` re-exported here for module-level reference if needed by future tests.
_ = _dispatch
