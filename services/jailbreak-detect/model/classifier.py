# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoGuard JailbreakDetect model.

A two-stage pipeline, reconstructed from the open artifacts so it can be served
independently of the NVIDIA NIM. The recipe below was validated against the
hosted NIM on build.nvidia.com (matching verdicts + ranking):

Stage 1 — ``SnowflakeEmbed``: the ``Snowflake/snowflake-arctic-embed-m-long``
transformer encoder, used as a frozen feature extractor. The input is prefixed
with the Arctic **query prefix** and the **CLS** token of the last hidden state
is taken (no L2 normalization). The prefix is essential — without it the random
forest sees out-of-distribution embeddings and classifies everything benign. The
NIM applies this prefix server-side; the open-source nemoguardrails code does
not, which is why its in-process path is inaccurate.

Stage 2 — ``JailbreakClassifier``: the scikit-learn **random forest**
``snowflake.pkl`` from the ``nvidia/NemoGuard-JailbreakDetect`` Hugging Face repo.
We use ``predict_proba`` (the pre-#1715 nemoguardrails behavior), NOT the
``snowflake.onnx`` export — that ONNX emits an uncalibrated decision function,
not probabilities. ``score`` matches the NIM's wire value, ``2*p1 - 1`` (negative
= benign, positive = jailbreak), and the verdict is ``p1 > 0.5``.

This module has no dependency on ``nemo_platform`` so the model container stays
lean; it is imported by both the standalone server (``server.py``) and the tests.
"""

from __future__ import annotations

import os
import pickle  # noqa: S403  # trusted, revision-pinned artifact from nvidia/NemoGuard-JailbreakDetect
from typing import Any

import numpy as np

# Pin exact commits for reproducibility and to avoid silently fetching new
# `trust_remote_code` model code on every load. Bump deliberately after review.
SNOWFLAKE_MODEL_ID = "Snowflake/snowflake-arctic-embed-m-long"
SNOWFLAKE_MODEL_REVISION = "92d97331f1f4b6a366c1f161354b9f3390cc219f"

MODEL_REPO_ID = "nvidia/NemoGuard-JailbreakDetect"
MODEL_REVISION = "cc8b97e2bd6c1667c31476eedaa9a75b4d7ed282"
MODEL_FILENAME = "snowflake.pkl"

# Arctic-embed query prefix. Required: the random forest was trained on embeddings
# produced with this prefix. Omitting it collapses jailbreak/benign separation.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Token budget and pooling strategy must stay bit-compatible with upstream,
# otherwise the random forest sees a different feature distribution and
# accuracy silently degrades.
_MAX_TOKENS = 2048


class SnowflakeEmbed:
    """Wraps the Snowflake Arctic embedding model (CLS pooling)."""

    def __init__(self, device: str | None = None) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        if device is None:
            device = os.environ.get("JAILBREAK_CHECK_DEVICE")
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        self.tokenizer = AutoTokenizer.from_pretrained(
            SNOWFLAKE_MODEL_ID,
            revision=SNOWFLAKE_MODEL_REVISION,
            trust_remote_code=True,
        )
        self.model = AutoModel.from_pretrained(
            SNOWFLAKE_MODEL_ID,
            revision=SNOWFLAKE_MODEL_REVISION,
            trust_remote_code=True,
            add_pooling_layer=False,
            # The repo ships safetensors only. The model's custom (nomic-bert)
            # loader reads `safe_serialization` (not `use_safetensors`); without
            # it the loader looks for a non-existent pytorch_model.bin and fails.
            use_safetensors=True,
            safe_serialization=True,
        )
        self.model.to(self.device)
        self.model.eval()

    def __call__(self, text: str) -> np.ndarray:
        tokens = self.tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=_MAX_TOKENS,
        )
        tokens = tokens.to(self.device)
        embeddings = self.model(**tokens)[0][:, 0]
        return embeddings.detach().cpu().squeeze(0).numpy()


class JailbreakClassifier:
    """Embedding + random-forest jailbreak classifier.

    Calling the instance with a prompt returns ``(is_jailbreak, score)``.
    ``score`` matches the NIM wire value ``2*p1 - 1`` (negative = benign,
    positive = jailbreak); ``is_jailbreak`` is ``p1 > 0.5``.
    """

    def __init__(self, device: str | None = None) -> None:
        from huggingface_hub import hf_hub_download

        self.embed = SnowflakeEmbed(device=device)
        # Mirror SnowflakeEmbed: fetch (and HF-cache) the random forest at a
        # pinned revision instead of requiring a caller-supplied path.
        random_forest_path = hf_hub_download(
            repo_id=MODEL_REPO_ID,
            filename=MODEL_FILENAME,
            revision=MODEL_REVISION,
        )
        with open(random_forest_path, "rb") as fd:
            self.classifier: Any = pickle.load(fd)  # noqa: S301  # trusted, revision-pinned RF

    def __call__(self, text: str) -> tuple[bool, float]:
        embedding = self.embed(QUERY_PREFIX + text)
        proba = self.classifier.predict_proba([embedding])[0]
        p1 = float(proba[1])
        # NIM-compatible signed score; verdict thresholds p1 at 0.5 (score at 0).
        score = 2.0 * p1 - 1.0
        return p1 > 0.5, score
