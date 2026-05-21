# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""`customizer.finetune` job — local fine-tuning with backend dispatch.

Registered under ``nemo.jobs``. The platform auto-mounts it as
``nemo customizer finetune run [flags...]``. Per-field flags
(``--backend``, ``--training-type``, ``--model``, ``--gpus``, ...) are
generated from :class:`FinetuneSpec` automatically.

The job is BYO-venv: the user provides a Python environment that has
the backend's heavy dependencies installed (Unsloth + PyTorch + ...).
They pass it via the core ``--venv`` flag, which re-execs the entire
CLI inside that interpreter; the child process then re-enters this
``run`` method with the right imports available and dispatches the
backend in-process.

If ``--venv`` is omitted and the calling interpreter does not satisfy
the backend's deps, ``run`` raises with a message instructing the user
how to set up a venv and which ``--venv`` value to pass next time.
The plugin does not auto-create venvs.
"""

from __future__ import annotations

from typing import Optional

from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from pydantic import BaseModel, Field, field_validator

_ALLOWED_TRAINING_TYPES = ("sft",)
_ALLOWED_BACKENDS = ("unsloth", "automodel", "megatron-bridge")


class FinetuneSpec(BaseModel):
    """Submitter-facing spec for `customizer.finetune`.

    Each scalar leaf becomes an auto-generated CLI flag under the
    "Job Spec" panel of ``nemo customizer finetune run --help``.

    ``training_type`` and ``backend`` are typed as ``str`` (not ``Literal``)
    on purpose: ``walk_spec_leaves`` in nemo-platform-plugin currently
    skips ``Literal`` fields when generating per-field CLI flags, and we
    want them surfaced as ``--training-type`` / ``--backend``. Validation
    happens via the validators below.
    """

    training_type: str = Field(
        "sft",
        description=f"Training algorithm. One of: {', '.join(_ALLOWED_TRAINING_TYPES)}.",
    )
    backend: str = Field(
        "unsloth",
        description=f"Training backend. One of: {', '.join(_ALLOWED_BACKENDS)}.",
    )
    model: str = Field(
        "unsloth/Qwen2.5-0.5B-Instruct",
        description="HF model id or local path. Defaults to a small model suitable for smoke tests.",
    )
    dataset_path: Optional[str] = Field(
        None,
        description="Path to a local JSONL dataset (or HF dataset id). When None, an inline 3-row smoke dataset is used.",
    )
    max_seq_length: int = Field(512, description="Max sequence length for tokenization.")
    max_steps: int = Field(1, description="Number of training steps. Defaults to 1 for smoke tests.")
    lora_rank: int = Field(8, description="LoRA rank.")
    lora_alpha: int = Field(16, description="LoRA alpha.")
    learning_rate: float = Field(2e-4, description="Optimizer learning rate.")
    gpus: Optional[str] = Field(
        None,
        description=(
            "GPU indices to expose to the backend, e.g. '0' or '0,1'. "
            "Sets CUDA_VISIBLE_DEVICES on the backend subprocess. Selection, not reservation."
        ),
    )

    @field_validator("training_type")
    @classmethod
    def _check_training_type(cls, v: str) -> str:
        if v not in _ALLOWED_TRAINING_TYPES:
            raise ValueError(f"training_type must be one of {_ALLOWED_TRAINING_TYPES}, got {v!r}")
        return v

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str) -> str:
        if v not in _ALLOWED_BACKENDS:
            raise ValueError(f"backend must be one of {_ALLOWED_BACKENDS}, got {v!r}")
        return v


class FinetuneJob(NemoJob):
    """Fine-tune a model locally via a backend-specific venv."""

    name = "finetune"
    description = "Fine-tune a model locally (unsloth implemented; automodel and megatron-bridge stubbed)."
    container = "gpu-tasks"
    execution_provider = "gpu"
    spec_schema = FinetuneSpec

    def run(self, config: dict, *, ctx: JobContext) -> dict:
        # Heavy imports kept inside run() so the parent process can introspect
        # this class for entry-point discovery without paying their cost.
        from nemo_customizer_plugin.backends._dispatch import dispatch_in_process
        from nemo_customizer_plugin.venv_resolver import (
            is_satisfied_locally,
            missing_venv_message,
        )

        spec = FinetuneSpec.model_validate(config)

        if not is_satisfied_locally(spec):
            raise RuntimeError(missing_venv_message(spec))

        return dispatch_in_process(spec, ctx)
