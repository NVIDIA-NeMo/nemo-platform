# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for shared job compile step helpers."""

from datetime import datetime

import pytest
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.entities.utils import get_random_id
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.customizer.shared.app.jobs.compile_steps import (
    StoragePaths,
    append_download_if_present,
    build_file_download_config,
    build_file_upload_config,
    build_output_fileset_metadata,
    require_fileset_for_download,
    resolve_deployment_config,
)

_PATHS = StoragePaths(
    model_path="/model",
    dataset_path="/dataset",
    output_model_path="/output",
    teacher_model_path="/teacher",
)


def _make_model_entity(**kwargs) -> ModelEntity:
    defaults = {
        "id": get_random_id("model"),
        "workspace": "default",
        "name": "test-model",
        "fileset": "fileset://default/base-model",
        "trust_remote_code": False,
        "finetuning_type": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    defaults.update(kwargs)
    return ModelEntity(**defaults)


def test_require_fileset_for_download_rejects_missing() -> None:
    with pytest.raises(PlatformJobCompilationError, match="has no fileset"):
        require_fileset_for_download(None, "Model 'default/test'")


def test_build_file_download_config_requires_model_when_flag_set() -> None:
    with pytest.raises(PlatformJobCompilationError, match="has no fileset"):
        build_file_download_config(
            model_fileset=None,
            dataset_path="fileset://default/dataset",
            paths=_PATHS,
            require_model_fileset=True,
            model_entity_label="Model 'default/test'",
        )


def test_build_file_download_config_includes_teacher_when_required() -> None:
    config = build_file_download_config(
        model_fileset="fileset://default/model",
        dataset_path="fileset://default/dataset",
        paths=_PATHS,
        teacher_fileset="fileset://default/teacher",
        require_teacher_fileset=True,
        teacher_entity_label="Teacher model 'default/teacher'",
    )
    assert len(config.download) == 3
    assert config.download[2].dest == "/teacher"


def test_build_file_upload_config_sets_metadata() -> None:
    metadata = {"tool_calling": {"chat_template": "test"}}
    config = build_file_upload_config("output-fs", "/output", metadata)
    assert config.upload[0].metadata == metadata


def test_build_output_fileset_metadata_returns_none_without_spec() -> None:
    me = _make_model_entity(spec=None)
    assert build_output_fileset_metadata(me) is None


def test_resolve_deployment_config_passes_string_through() -> None:
    assert resolve_deployment_config("my-config", dict) == "my-config"


def test_append_download_if_present_skips_empty() -> None:
    downloads = []
    append_download_if_present(downloads, None, "/dest", "model")
    assert downloads == []
