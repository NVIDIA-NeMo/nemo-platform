# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest
from nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.adapter_resolution import (
    EMBEDDED_RUN_CONFIG_NAME,
    embed_run_config_in_adapter,
    is_adapter_reuse_requested,
    is_peft_adapter_directory,
    resolve_prior_training_workdir,
)


def _write_adapter_dir(tmp_path: Path, *, include_metadata: bool = True) -> Path:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"stub")
    if include_metadata:
        (adapter_dir / "metadata_v2.json").write_text(
            json.dumps(
                {
                    "workdir": {
                        "config_name": "default",
                        "dataset_name": "data",
                        "run_name": "2026-01-01T00:00:00",
                    }
                }
            ),
            encoding="utf-8",
        )
    return adapter_dir


def test_is_peft_adapter_directory(tmp_path):
    adapter_dir = _write_adapter_dir(tmp_path)
    assert is_peft_adapter_directory(adapter_dir)
    assert not is_peft_adapter_directory(tmp_path / "missing")


def test_embed_run_config_in_adapter(tmp_path):
    run_root = tmp_path / "run"
    train_dir = run_root / "train"
    adapter_dir = train_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (train_dir / EMBEDDED_RUN_CONFIG_NAME).write_text('{"generation": {"num_records": 1}}', encoding="utf-8")

    embed_run_config_in_adapter(adapter_dir)

    assert (adapter_dir / EMBEDDED_RUN_CONFIG_NAME).is_file()


def test_resolve_prior_training_workdir_from_output_adapter_copy(tmp_path, monkeypatch):
    output_dir = tmp_path / "nss-output"
    work_dir = output_dir / "work" / "default---data" / "2026-01-01T00:00:00"
    adapter_dir = work_dir / "train" / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"stub")
    (work_dir / "dataset").mkdir()
    (work_dir / "dataset" / "training.csv").write_text("value\n1\n", encoding="utf-8")
    (work_dir / "train" / EMBEDDED_RUN_CONFIG_NAME).write_text("{}", encoding="utf-8")
    (adapter_dir / "metadata_v2.json").write_text("{}", encoding="utf-8")

    copied_adapter = _write_adapter_dir(output_dir, include_metadata=True)

    monkeypatch.chdir(tmp_path)
    workdir = resolve_prior_training_workdir("./nss-output/adapter")
    assert workdir.adapter_path == adapter_dir
    assert copied_adapter.is_dir()


def test_materialize_workdir_from_downloaded_adapter(tmp_path):
    adapter_dir = _write_adapter_dir(tmp_path)
    (adapter_dir / EMBEDDED_RUN_CONFIG_NAME).write_text("{}", encoding="utf-8")

    workdir = resolve_prior_training_workdir(adapter_dir)
    assert workdir.adapter_path.is_dir()
    assert (workdir.train.config).is_file()


def test_is_adapter_reuse_requested_for_local_adapter(tmp_path, monkeypatch):
    pytest.importorskip("nemo_safe_synthesizer.config.job")
    from nemo_safe_synthesizer_plugin.api.v2.jobs.endpoints import SafeSynthesizerJobConfig

    output_dir = tmp_path / "nss-output"
    _write_adapter_dir(output_dir)
    work_dir = output_dir / "work" / "default---data" / "2026-01-01T00:00:00" / "train" / "adapter"
    work_dir.mkdir(parents=True)
    (work_dir / "adapter_model.safetensors").write_bytes(b"stub")

    monkeypatch.chdir(tmp_path)
    job_config = SafeSynthesizerJobConfig.model_validate(
        {
            "data_source": "default/data#input.csv",
            "config": {"training": {"pretrained_model": "./nss-output/adapter"}},
        }
    )
    assert is_adapter_reuse_requested(job_config) is True


def test_is_adapter_reuse_requested_for_pretrained_model_job(tmp_path):
    pytest.importorskip("nemo_safe_synthesizer.config.job")
    from nemo_safe_synthesizer_plugin.api.v2.jobs.endpoints import SafeSynthesizerJobConfig

    job_config = SafeSynthesizerJobConfig.model_validate(
        {
            "data_source": "default/data#input.csv",
            "pretrained_model_job": "prior-safe-synth-job",
            "config": {},
        }
    )
    assert is_adapter_reuse_requested(job_config) is True
