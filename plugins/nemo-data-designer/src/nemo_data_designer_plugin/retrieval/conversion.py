# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from nemo_data_designer_plugin.retrieval.manifest import resolve_generation_input

if TYPE_CHECKING:
    from data_designer_retrieval_sdg import ConversionResult

RETRIEVAL_SDG_SCHEMA_VERSION = 1


def execute_conversion(
    input_path: Path,
    output_dir: Path,
    corpus_id: str,
    quality_threshold: float,
    train_ratio: float,
    val_ratio: float,
    seed: int,
    max_pos_docs: int,
    use_group_id_in_eval: bool,
    split_strategy: Literal["random", "dedupped", "cluster"],
) -> ConversionResult:
    """Convert Stage 0 JSONL (or a generation manifest) into train/eval BEIR artifacts."""
    from data_designer_retrieval_sdg import ConversionRunConfig, run_conversion_with_config

    resolved = resolve_generation_input(input_path)
    config = ConversionRunConfig(
        schema_version=RETRIEVAL_SDG_SCHEMA_VERSION,
        input_path=resolved,
        corpus_id=corpus_id,
        output_dir=output_dir.resolve(),
        eval_only=False,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        seed=seed,
        quality_threshold=quality_threshold,
        max_pos_docs=max_pos_docs,
        use_group_id_in_eval=use_group_id_in_eval,
        split_strategy=split_strategy,
    )
    return run_conversion_with_config(config)
