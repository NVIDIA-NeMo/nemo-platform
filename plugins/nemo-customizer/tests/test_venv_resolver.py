# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nemo_customizer_plugin.venv_resolver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nemo_customizer_plugin.jobs.finetune import FinetuneSpec
from nemo_customizer_plugin.venv_resolver import (
    default_venv_path,
    extra_for_spec,
    is_satisfied_locally,
    missing_venv_message,
    probe_venv,
)


class TestExtraForSpec:
    @pytest.mark.parametrize(
        "training_type,backend,expected",
        [
            ("sft", "unsloth", "unsloth"),
            ("sft", "automodel", "automodel"),
            ("sft", "megatron-bridge", "megatron-bridge"),
        ],
    )
    def test_known_combinations(self, training_type, backend, expected):
        spec = FinetuneSpec(training_type=training_type, backend=backend)
        assert extra_for_spec(spec) == expected


class TestIsSatisfiedLocally:
    def test_returns_true_when_marker_findable(self):
        spec = FinetuneSpec(training_type="sft", backend="unsloth")
        with patch(
            "nemo_customizer_plugin.venv_resolver.importlib.util.find_spec",
            return_value=MagicMock(),
        ) as m:
            assert is_satisfied_locally(spec) is True
            m.assert_called_once_with("unsloth")

    def test_returns_false_when_marker_missing(self):
        spec = FinetuneSpec(training_type="sft", backend="unsloth")
        with patch(
            "nemo_customizer_plugin.venv_resolver.importlib.util.find_spec",
            return_value=None,
        ):
            assert is_satisfied_locally(spec) is False

    def test_unsloth_marker(self):
        """Marker for unsloth backend is the 'unsloth' module."""
        spec = FinetuneSpec(training_type="sft", backend="unsloth")
        with patch("nemo_customizer_plugin.venv_resolver.importlib.util.find_spec") as m:
            is_satisfied_locally(spec)
            m.assert_called_once_with("unsloth")

    def test_automodel_marker(self):
        spec = FinetuneSpec(training_type="sft", backend="automodel")
        with patch("nemo_customizer_plugin.venv_resolver.importlib.util.find_spec") as m:
            is_satisfied_locally(spec)
            m.assert_called_once_with("nemo_automodel")


class TestDefaultVenvPath:
    def test_unsloth_path(self):
        path = default_venv_path("unsloth")
        assert path == Path.home() / ".nemo" / "customizer" / "unsloth" / ".venv"

    def test_automodel_path(self):
        path = default_venv_path("automodel")
        assert path.parts[-2:] == ("automodel", ".venv")


class TestProbeVenv:
    def test_missing_interpreter_returns_false(self, tmp_path):
        ok, detail = probe_venv(tmp_path / "nonexistent", "unsloth")
        assert ok is False
        assert "no executable interpreter" in detail

    def test_probe_invokes_subprocess_with_right_modules(self, tmp_path, monkeypatch):
        """When the venv has an executable python, probe runs the right import statement."""
        # Create a fake venv layout
        venv_dir = tmp_path / "fake-venv"
        (venv_dir / "bin").mkdir(parents=True)
        fake_python = venv_dir / "bin" / "python"
        fake_python.touch()
        fake_python.chmod(0o755)

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch("nemo_customizer_plugin.venv_resolver.subprocess.run", side_effect=fake_run):
            ok, detail = probe_venv(venv_dir, "unsloth")

        assert ok is True
        assert captured["cmd"][0] == str(fake_python)
        assert captured["cmd"][1] == "-c"
        assert "import nemo_platform" in captured["cmd"][2]
        assert "import nemo_customizer_plugin" in captured["cmd"][2]
        assert "import unsloth" in captured["cmd"][2]

    def test_probe_returns_false_on_import_failure(self, tmp_path):
        venv_dir = tmp_path / "fake-venv"
        (venv_dir / "bin").mkdir(parents=True)
        fake_python = venv_dir / "bin" / "python"
        fake_python.touch()
        fake_python.chmod(0o755)

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "ModuleNotFoundError: No module named 'unsloth'"
            return result

        with patch("nemo_customizer_plugin.venv_resolver.subprocess.run", side_effect=fake_run):
            ok, detail = probe_venv(venv_dir, "unsloth")

        assert ok is False
        assert "unsloth" in detail


class TestMissingVenvMessage:
    def test_message_mentions_extra_and_default_path(self):
        spec = FinetuneSpec(training_type="sft", backend="unsloth")
        msg = missing_venv_message(spec)
        assert "unsloth" in msg
        assert "--venv" in msg
        assert "uv venv" in msg
        assert "[unsloth]" in msg
        assert str(default_venv_path("unsloth")) in msg

    def test_message_uses_correct_extra_per_backend(self):
        spec = FinetuneSpec(training_type="sft", backend="automodel")
        msg = missing_venv_message(spec)
        assert "[automodel]" in msg
