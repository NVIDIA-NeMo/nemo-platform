# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth SFT backend.

All heavyweight imports (``unsloth``, ``torch``, ``transformers``,
``trl``, ``peft``) are intentionally inside ``train_sft`` so the parent
process can import this module for entry-point dispatch without
dragging in ML deps.

Unsloth's ``import unsloth`` must happen before ``transformers`` is
imported — it monkey-patches the transformer modules at import time.
Out-of-order imports silently degrade performance.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_platform_plugin.job_context import JobContext

    from nemo_customizer_plugin.jobs.finetune import FinetuneSpec

logger = logging.getLogger(__name__)


def train_sft(spec: "FinetuneSpec", ctx: "JobContext") -> dict:
    """Run one (or more) SFT steps with Unsloth's FastLanguageModel + LoRA."""
    # ── Heavy imports — local to this function ─────────────────────────
    # NB: `unsloth` must be imported BEFORE transformers/peft/trl.
    import unsloth  # noqa: F401  (import-side-effects required)
    from datasets import Dataset
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from unsloth import FastLanguageModel

    logger.info(
        "Unsloth SFT: model=%s max_seq_length=%d max_steps=%d lora=(r=%d, alpha=%d) cuda_visible=%s",
        spec.model,
        spec.max_seq_length,
        spec.max_steps,
        spec.lora_rank,
        spec.lora_alpha,
        os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>"),
    )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=spec.model,
        max_seq_length=spec.max_seq_length,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=spec.lora_rank,
        lora_alpha=spec.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    if spec.dataset_path:
        ds = Dataset.from_json(spec.dataset_path)
    else:
        ds = _inline_smoke_dataset(tokenizer)

    output_dir = ctx.storage.persistent / "customizer_out"
    output_dir.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=1,
        max_steps=spec.max_steps,
        logging_steps=1,
        learning_rate=spec.learning_rate,
        report_to="none",
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        dataset_text_field="text",
        max_seq_length=spec.max_seq_length,
        args=args,
    )
    result = trainer.train()

    return {
        "loss": float(result.training_loss),
        "steps": int(spec.max_steps),
        "model": spec.model,
        "backend": "unsloth",
        "output_dir": str(output_dir),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def _inline_smoke_dataset(tokenizer):
    """3-row chat dataset for smoke tests when no dataset_path is supplied."""
    from datasets import Dataset

    examples = [
        ("What is 2+2?", "4."),
        ("Capital of France?", "Paris."),
        ("Say hello.", "Hello!"),
    ]
    rows = [
        {
            "text": tokenizer.apply_chat_template(
                [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": a},
                ],
                tokenize=False,
            )
        }
        for q, a in examples
    ]
    return Dataset.from_list(rows)
