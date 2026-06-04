# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nmp.customizer.shared.app.jobs.context import NMPJobContext
from nmp.customizer.shared.app.jobs.file_io.schemas import FileSetRef
from nmp.customizer.shared.entities.values import FinetuningType


def test_fileset_ref_parses_bare_name() -> None:
    ref = FileSetRef.model_validate("my-dataset")
    assert ref.workspace is None
    assert ref.name == "my-dataset"


def test_finetuning_type_values() -> None:
    assert FinetuningType.LORA.value == "lora"


def test_job_context_defaults() -> None:
    ctx = NMPJobContext.from_env()
    assert ctx.workspace
    assert ctx.normalized_task.startswith("task-") or ctx.task.startswith("task-")
