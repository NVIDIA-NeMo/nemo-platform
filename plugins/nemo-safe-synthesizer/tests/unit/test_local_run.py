# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _resp(data):
    """Wrap a payload in a NemoResponse-like object whose ``.data()`` returns it.

    Production consumes typed-client responses via ``client.<op>(...).data()``.
    """
    m = MagicMock()
    m.data.return_value = data
    return m


def import_task_main_without_heavy_runtime(monkeypatch):
    pytest.importorskip("nemo_safe_synthesizer.config.job")
    library_builder = ModuleType("nemo_safe_synthesizer.sdk.library_builder")
    setattr(library_builder, "SafeSynthesizer", object)
    monkeypatch.setitem(sys.modules, "nemo_safe_synthesizer.sdk.library_builder", library_builder)
    return importlib.import_module("nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.__main__")


def test_run_local_loads_spec_and_writes_results(tmp_path, monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(
            {
                "data_source": "default/data#input.csv",
                "config": {
                    "enable_synthesis": False,
                    "enable_replace_pii": False,
                },
            }
        ),
        encoding="utf-8",
    )
    data_file = tmp_path / "input.csv"
    data_file.write_text("value\n1\n", encoding="utf-8")

    result = SimpleNamespace(
        synthetic_data=pd.DataFrame({"value": [1]}),
        summary=SimpleNamespace(model_dump=lambda: {"row_count": 1}),
        evaluation_report_html=None,
    )
    monkeypatch.setattr(
        task_main,
        "run_config",
        lambda job_config, data_source, save_path, *, adapter_location=None: (result, None),
    )
    get_platform_sdk = MagicMock(side_effect=AssertionError("offline run should not initialize the platform SDK"))
    monkeypatch.setattr(task_main, "get_platform_sdk", get_platform_sdk)

    output_dir = tmp_path / "output"
    task_main.run_local(spec_file=spec_file, workspace="default", output_dir=output_dir, data_source=data_file)

    assert (output_dir / "synthetic-data.csv").exists()
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == {"row_count": 1}
    get_platform_sdk.assert_not_called()


def test_run_from_env_reports_missing_config_path(monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    monkeypatch.setattr(task_main, "initialize_observability", lambda: None)
    monkeypatch.setattr(task_main, "get_platform_config", lambda: SimpleNamespace(get_service_url=lambda _name: None))
    monkeypatch.setattr(task_main, "_setup_classify_endpoint", lambda: None)
    monkeypatch.setattr(task_main, "download_from_fileset", lambda fileset_url: pd.DataFrame({"value": [1]}))
    monkeypatch.setenv("DATA_SOURCE", "default/data#input.csv")
    monkeypatch.delenv(task_main.NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, raising=False)

    with pytest.raises(ValueError, match=f"{task_main.NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR} is not set"):
        task_main.run_from_env()


def test_setup_classify_endpoint_sets_upstream_safe_synthesizer_env(monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    monkeypatch.setenv(
        "CLASSIFY_LLM_ENDPOINT_PATH", "/apis/inference-gateway/v2/workspaces/default/provider/my-nim/-/v1"
    )
    monkeypatch.setenv("NMP_MODELS_URL", "http://models.test")
    monkeypatch.delenv("NSS_INFERENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("NSS_INFERENCE_KEY", raising=False)

    task_main._setup_classify_endpoint()

    assert (
        task_main.os.environ["NSS_INFERENCE_ENDPOINT"]
        == "http://models.test/apis/inference-gateway/v2/workspaces/default/provider/my-nim/-/v1"
    )
    assert task_main.os.environ["NSS_INFERENCE_KEY"] == "not-needed"


def test_setup_classify_endpoint_preserves_existing_inference_key(monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    monkeypatch.setenv("CLASSIFY_LLM_ENDPOINT_PATH", "/route")
    monkeypatch.setenv("NMP_MODELS_URL", "http://models.test/")
    monkeypatch.setenv("NSS_INFERENCE_KEY", "real-key")

    task_main._setup_classify_endpoint()

    assert task_main.os.environ["NSS_INFERENCE_ENDPOINT"] == "http://models.test/route"
    assert task_main.os.environ["NSS_INFERENCE_KEY"] == "real-key"


def test_run_local_resolves_pretrained_model_job_before_run(tmp_path, monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(
            {
                "data_source": "default/data#input.csv",
                "pretrained_model_job": "prior-safe-synth-job",
                "config": {
                    "enable_synthesis": False,
                    "enable_replace_pii": False,
                },
            }
        ),
        encoding="utf-8",
    )
    data_file = tmp_path / "input.csv"
    data_file.write_text("value\n1\n", encoding="utf-8")

    adapter_dir = tmp_path / "downloaded-adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "HuggingFaceTB/SmolLM3-3B"}),
        encoding="utf-8",
    )

    sdk = MagicMock()
    monkeypatch.setattr(task_main, "get_platform_sdk", lambda: sdk)

    # Production resolves the prior adapter via
    # client_from_platform(sdk, JobsClient).get_job_result(...).data().
    jobs_client = MagicMock()
    jobs_client.get_job_result.return_value = _resp(
        SimpleNamespace(artifact_url="default/job-results-prior#results/attempt-1/adapter")
    )
    monkeypatch.setattr(task_main, "client_from_platform", lambda _sdk, _cls: jobs_client)

    file_manager = MagicMock()
    file_manager.download_from_url.return_value = SimpleNamespace(
        path=adapter_dir,
        cleanup_tmp_dir=MagicMock(),
    )
    monkeypatch.setattr(task_main, "FilesetFileManager", MagicMock(return_value=file_manager))

    captured = {}
    result = SimpleNamespace(
        synthetic_data=pd.DataFrame({"value": [1]}),
        summary=SimpleNamespace(model_dump=lambda: {"row_count": 1}),
        evaluation_report_html=None,
    )

    def fake_run_config(job_config, data_source, save_path, *, adapter_location=None):
        captured["adapter_location"] = adapter_location
        return result, None

    monkeypatch.setattr(task_main, "run_config", fake_run_config)

    output_dir = tmp_path / "output"
    task_main.run_local(spec_file=spec_file, workspace="default", output_dir=output_dir, data_source=data_file)

    assert captured["adapter_location"] == adapter_dir
    jobs_client.get_job_result.assert_called_once_with(
        name="adapter",
        job="prior-safe-synth-job",
        workspace="default",
    )


def test_run_local_cleans_pretrained_model_tmp_when_run_config_raises(tmp_path, monkeypatch):
    task_main = import_task_main_without_heavy_runtime(monkeypatch)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(
            {
                "data_source": "default/data#input.csv",
                "pretrained_model_job": "prior-safe-synth-job",
                "config": {
                    "enable_synthesis": False,
                    "enable_replace_pii": False,
                },
            }
        ),
        encoding="utf-8",
    )
    data_file = tmp_path / "input.csv"
    data_file.write_text("value\n1\n", encoding="utf-8")

    adapter_dir = tmp_path / "downloaded-adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "HuggingFaceTB/SmolLM3-3B"}),
        encoding="utf-8",
    )

    sdk = MagicMock()
    monkeypatch.setattr(task_main, "get_platform_sdk", lambda: sdk)

    # Production resolves the prior adapter via
    # client_from_platform(sdk, JobsClient).get_job_result(...).data().
    jobs_client = MagicMock()
    jobs_client.get_job_result.return_value = _resp(
        SimpleNamespace(artifact_url="default/job-results-prior#results/attempt-1/adapter")
    )
    monkeypatch.setattr(task_main, "client_from_platform", lambda _sdk, _cls: jobs_client)

    pretrained_model_tmp = SimpleNamespace(
        path=adapter_dir,
        cleanup_tmp_dir=MagicMock(),
    )
    file_manager = MagicMock()
    file_manager.download_from_url.return_value = pretrained_model_tmp
    monkeypatch.setattr(task_main, "FilesetFileManager", MagicMock(return_value=file_manager))

    def raise_run_config(job_config, data_source, save_path, *, adapter_location=None):
        raise RuntimeError("run_config failed")

    monkeypatch.setattr(task_main, "run_config", raise_run_config)

    output_dir = tmp_path / "output"
    with pytest.raises(RuntimeError, match="run_config failed"):
        task_main.run_local(spec_file=spec_file, workspace="default", output_dir=output_dir, data_source=data_file)

    pretrained_model_tmp.cleanup_tmp_dir.assert_called_once_with()
