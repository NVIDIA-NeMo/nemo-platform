# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock, patch

from nemo_platform.cli.telemetry import emit as emit_mod
from nemo_platform.cli.telemetry.events import CommandInvokedEvent, TaskStatusEnum


def _event():
    return CommandInvokedEvent(command="docs", task_status=TaskStatusEnum.COMPLETED, duration_sec=0.1)


class TestOptOutLayers:
    def test_env_layer(self, monkeypatch):
        monkeypatch.setenv("NEMO_TELEMETRY_ENABLED", "false")
        assert emit_mod.telemetry_opted_in() is False

    def test_config_layer(self, monkeypatch, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("telemetry_enabled: false\n")
        monkeypatch.setenv("NMP_CONFIG_FILE", str(cfg))
        assert emit_mod.telemetry_opted_in() is False

    def test_invocation_flag_layer(self):
        emit_mod.set_invocation_opt_out(True)
        try:
            assert emit_mod.telemetry_opted_in() is False
        finally:
            emit_mod.set_invocation_opt_out(False)

    def test_default_is_on(self):
        assert emit_mod.telemetry_opted_in() is True

    def test_config_load_error_fails_closed(self, monkeypatch):
        """A broken/parse-error config must fail closed (opted out), not default to on."""
        from nemo_platform.config import config as config_mod

        def boom(*args, **kwargs):
            raise RuntimeError("broken config")

        monkeypatch.setattr(config_mod.Config, "load", boom)
        assert emit_mod.telemetry_opted_in() is False


class TestEmitEvent:
    @patch.object(emit_mod, "TelemetryHandler")
    def test_emit_enqueues_and_stops(self, handler_cls):
        instance = Mock()
        handler_cls.return_value = instance
        emit_mod.emit_event(_event())
        instance.enqueue.assert_called_once()
        instance.stop.assert_called_once()

    @patch.object(emit_mod, "TelemetryHandler")
    def test_emit_skipped_when_opted_out(self, handler_cls, monkeypatch):
        monkeypatch.setenv("NEMO_TELEMETRY_ENABLED", "0")
        emit_mod.emit_event(_event())
        handler_cls.assert_not_called()

    @patch.object(emit_mod, "TelemetryHandler", side_effect=RuntimeError("boom"))
    def test_emit_never_raises(self, handler_cls):
        emit_mod.emit_event(_event())  # must not raise

    @patch.object(emit_mod, "TelemetryHandler")
    def test_session_id_is_stable_across_calls(self, handler_cls):
        """Every event in one process shares the per-process session id."""
        emit_mod.emit_event(_event())
        emit_mod.emit_event(_event())
        session_ids = [call.kwargs["session_id"] for call in handler_cls.call_args_list]
        assert len(session_ids) == 2
        assert session_ids[0] == session_ids[1] == emit_mod._SESSION_ID


class TestFirstRunNotice:
    def test_notice_printed_once_to_stderr(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setattr(emit_mod, "_notice_marker_path", lambda: tmp_path / "telemetry-notice-shown")
        emit_mod.maybe_print_first_run_notice()
        first = capsys.readouterr()
        assert "anonymous usage data" in first.err
        assert first.out == ""  # stderr only; stdout stays machine-clean
        emit_mod.maybe_print_first_run_notice()
        assert capsys.readouterr().err == ""

    def test_no_notice_when_opted_out(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("NEMO_TELEMETRY_ENABLED", "false")
        monkeypatch.setattr(emit_mod, "_notice_marker_path", lambda: tmp_path / "telemetry-notice-shown")
        emit_mod.maybe_print_first_run_notice()
        assert capsys.readouterr().err == ""
