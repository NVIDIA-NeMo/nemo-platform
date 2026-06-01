# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, call

import pandas as pd
import pytest
from nmp.common.jobs.constants import NEMO_JOB_ID_ENVVAR, NEMO_JOB_WORKSPACE_ENVVAR


def import_task_main_without_heavy_runtime(monkeypatch):
    pytest.importorskip("nemo_safe_synthesizer.config.job")
    library_builder = ModuleType("nemo_safe_synthesizer.sdk.library_builder")
    setattr(library_builder, "SafeSynthesizer", MagicMock())
    monkeypatch.setitem(sys.modules, "nemo_safe_synthesizer.sdk.library_builder", library_builder)
    return importlib.import_module("nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.__main__")


def test_upload_results_uploads_and_registers_adapter(tmp_path, monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)

    monkeypatch.setenv(NEMO_JOB_ID_ENVVAR, "safe-synth-job")
    monkeypatch.setenv(NEMO_JOB_WORKSPACE_ENVVAR, "test-workspace")

    adapter_path = tmp_path / "adapter"
    adapter_path.mkdir()
    (adapter_path / "adapter_config.json").write_text("{}", encoding="utf-8")

    sdk = MagicMock()
    sdk.jobs.retrieve.return_value = SimpleNamespace(attempt_id="attempt-123")
    monkeypatch.setattr(task_main, "get_platform_sdk", lambda: sdk)

    file_manager = MagicMock()
    file_manager.upload.side_effect = lambda _local_path, remote_path: (
        f"test-workspace/job-results-safe-synth-job#{remote_path}"
    )
    fileset_manager_cls = MagicMock(return_value=file_manager)
    monkeypatch.setattr(task_main, "FilesetFileManager", fileset_manager_cls)

    result = SimpleNamespace(
        synthetic_data=pd.DataFrame({"value": [1]}),
        summary=SimpleNamespace(model_dump=lambda: {"row_count": 1}),
        evaluation_report_html=None,
    )

    task_main.upload_results(result=result, adapter_path=adapter_path)

    fileset_manager_cls.assert_called_once_with(
        workspace="test-workspace",
        fileset_name="job-results-safe-synth-job",
        sdk=sdk,
        ensure_fileset_exists=True,
    )
    file_manager.validate_storage.assert_called_once_with()
    file_manager.upload.assert_has_calls([call(adapter_path, "results/attempt-123/adapter")], any_order=True)
    sdk.jobs.results.create.assert_any_call(
        name="adapter",
        job="safe-synth-job",
        workspace="test-workspace",
        artifact_url="test-workspace/job-results-safe-synth-job#results/attempt-123/adapter",
        artifact_storage_type="fileset",
    )
