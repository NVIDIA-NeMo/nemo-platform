# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend dispatch — in-process only.

Once ``FinetuneJob.run`` has confirmed the current interpreter has the
backend's deps available (via ``is_satisfied_locally``), control lands
here. The single entry point branches on ``spec.backend`` and imports
the backend module lazily — heavy imports (unsloth, torch, transformers,
trl) are pushed into the branch arms so the parent process can
``import nemo_customizer_plugin.backends._dispatch`` for entry-point
discovery without paying their cost.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_platform_plugin.job_context import JobContext

    from nemo_customizer_plugin.jobs.finetune import FinetuneSpec

logger = logging.getLogger(__name__)


def dispatch_in_process(spec: "FinetuneSpec", ctx: "JobContext") -> dict:
    """Import the right backend module and invoke its ``train_sft``.

    All heavy imports happen inside the branch arms so the parent
    process can import this module without dragging in
    unsloth/torch/transformers.

    ``CUDA_VISIBLE_DEVICES`` is set from ``spec.gpus`` before the heavy
    import. Once torch is imported the variable is frozen, so setting it
    later has no effect.
    """
    if spec.gpus is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = spec.gpus
        logger.info("Set CUDA_VISIBLE_DEVICES=%s before backend import", spec.gpus)

    if spec.backend == "unsloth":
        from nemo_customizer_plugin.backends import unsloth as backend_mod
    elif spec.backend == "automodel":
        from nemo_customizer_plugin.backends import automodel as backend_mod
    elif spec.backend == "megatron-bridge":
        from nemo_customizer_plugin.backends import megatron_bridge as backend_mod
    else:
        raise ValueError(f"Unknown backend: {spec.backend!r}")

    if spec.training_type == "sft":
        return backend_mod.train_sft(spec, ctx)
    raise ValueError(f"Unsupported training_type: {spec.training_type!r}")
