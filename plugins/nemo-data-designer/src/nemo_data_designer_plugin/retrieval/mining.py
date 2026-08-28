# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_MINING_SCRIPT = Path(__file__).with_name("mine_hard_negatives.py")
_MINING_CONFIG = Path(__file__).with_name("mining_config.yaml")


def run_hard_negative_mining(
    *,
    train_file: Path,
    output_file: Path,
    cache_dir: Path,
    base_model: str,
    hard_negatives_to_mine: int,
    hard_neg_margin: float,
    mining_batch_size: int,
    query_prefix: str,
    passage_prefix: str,
    query_max_length: int,
    passage_max_length: int,
    attn_implementation: str,
    trust_remote_code: bool,
) -> Path:
    """Run Nemotron-style distributed hard-negative mining via torch.distributed.run."""
    cmd = [
        sys.executable,
        "-m",
        "torch.distributed.run",
        "--nproc_per_node",
        "gpu",
        str(_MINING_SCRIPT),
        "--config",
        str(_MINING_CONFIG),
        "--mining.model_name_or_path",
        base_model,
        "--mining.train_qa_file_path",
        str(train_file),
        "--mining.train_file_output_path",
        str(output_file),
        "--mining.cache_embeddings_dir",
        str(cache_dir),
        "--mining.hard_neg_margin",
        str(hard_neg_margin),
        "--mining.hard_negatives_to_mine",
        str(hard_negatives_to_mine),
        "--mining.mining_batch_size",
        str(mining_batch_size),
        "--mining.query_prefix",
        query_prefix,
        "--mining.passage_prefix",
        passage_prefix,
        "--mining.query_max_length",
        str(query_max_length),
        "--mining.passage_max_length",
        str(passage_max_length),
        "--mining.attn_implementation",
        attn_implementation,
        "--mining.trust_remote_code",
        str(trust_remote_code).lower(),
        "--mining.add_bos_token",
        "true",
        "--mining.add_eos_token",
        "false",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr or result.stdout or f"exit {result.returncode}"
        raise RuntimeError(f"Hard-negative mining failed: {detail}")
    return output_file
