# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoGuard JailbreakDetect model.

A two-stage pipeline built from the open-weights artifacts published on Hugging Face:

Stage 1 — ``SnowflakeEmbed``: the ``Snowflake/snowflake-arctic-embed-m-long``
transformer encoder, used as a frozen feature extractor; CLS token of the last
hidden state, no L2 normalization, ``max_length=2048``.

Stage 2 — ``JailbreakClassifier``: a scikit-learn **random forest** via
``predict_proba``. Verdict is ``argmax(proba)``; the ``score`` is the signed max-probability
(``-p0`` when benign, ``+p1`` when jailbreak). The classifier is the **open-weights** ``snowflake.pkl``
from the ``nvidia/NemoGuard-JailbreakDetect`` HF repo.
"""

from __future__ import annotations

import logging
import os
import pickle  # noqa: S403  # trusted, revision-pinned artifact from nvidia/NemoGuard-JailbreakDetect
from typing import Any, no_type_check

import numpy as np

logger = logging.getLogger(__name__)

# Pin exact commits for reproducibility and to avoid silently fetching new
# `trust_remote_code` model code on every load. Bump deliberately after review.
SNOWFLAKE_MODEL_ID = "Snowflake/snowflake-arctic-embed-m-long"
SNOWFLAKE_MODEL_REVISION = "92d97331f1f4b6a366c1f161354b9f3390cc219f"

MODEL_REPO_ID = "nvidia/NemoGuard-JailbreakDetect"
MODEL_REVISION = "cc8b97e2bd6c1667c31476eedaa9a75b4d7ed282"
MODEL_FILENAME = "snowflake.pkl"  # sklearn RandomForest (predict_proba) — the default
ONNX_FILENAME = "snowflake.onnx"  # used only by the doc-only JailbreakClassifierONNX (not served)

# Token budget and pooling strategy must match what the random forest was trained on;
# otherwise it sees a different feature distribution and accuracy silently degrades.
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

        logger.info(
            "Loading embedder %s (device=%s). First run downloads ~0.5 GB from "
            "Hugging Face and may take a few minutes...",
            SNOWFLAKE_MODEL_ID,
            device,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            SNOWFLAKE_MODEL_ID,
            revision=SNOWFLAKE_MODEL_REVISION,
            trust_remote_code=True,
        )
        if tokenizer is None:
            raise RuntimeError(f"Failed to load tokenizer for {SNOWFLAKE_MODEL_ID}")
        self.tokenizer = tokenizer
        logger.info("Tokenizer ready; loading embedder weights...")
        self.model = AutoModel.from_pretrained(
            SNOWFLAKE_MODEL_ID,
            revision=SNOWFLAKE_MODEL_REVISION,
            trust_remote_code=True,
            use_safetensors=True,
            safe_serialization=True,
            add_pooling_layer=False,
        )
        self.model.to(self.device)
        self.model.eval()
        logger.info("Embedder ready (device=%s).", device)

    def __call__(self, text: str) -> np.ndarray:
        import torch

        tokens = self.tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=_MAX_TOKENS,
        )
        tokens = tokens.to(self.device)
        with torch.inference_mode():
            embeddings = self.model(**tokens)[0][:, 0]
        return embeddings.detach().cpu().squeeze(0).numpy()


class JailbreakClassifier:
    """Embedding + random-forest jailbreak classifier.

    Calling the instance with a prompt returns ``(is_jailbreak, score)``.
    ``score`` is the signed max-probability (``-p0`` when benign, ``+p1``
    when jailbreak); ``is_jailbreak`` is ``argmax(proba) == 1`` (i.e. ``p1 > 0.5``).
    """

    def __init__(self, device: str | None = None, embed: SnowflakeEmbed | None = None) -> None:
        from huggingface_hub import hf_hub_download

        logger.info("Initializing jailbreak classifier (sklearn pkl)...")
        # `embed` lets callers share one loaded embedder across classifier variants.
        self.embed = embed if embed is not None else SnowflakeEmbed(device=device)
        # Like SnowflakeEmbed, fetch (and HF-cache) the random forest at a
        # pinned revision instead of requiring a caller-supplied path.
        logger.info("Loading random forest %s from %s...", MODEL_FILENAME, MODEL_REPO_ID)
        random_forest_path = hf_hub_download(
            repo_id=MODEL_REPO_ID,
            filename=MODEL_FILENAME,
            revision=MODEL_REVISION,
        )
        with open(random_forest_path, "rb") as fd:
            self.classifier: Any = pickle.load(fd)  # noqa: S301  # trusted, revision-pinned RF
        logger.info("Jailbreak classifier ready.")

    def __call__(self, text: str) -> tuple[bool, float]:
        embedding = self.embed(text)
        proba = self.classifier.predict_proba([embedding])[0]
        class_idx = int(np.argmax(proba))
        prob = float(proba[class_idx])
        score = -prob if class_idx == 0 else prob
        return bool(class_idx), score


class JailbreakClassifierONNX:
    """ONNX-runtime variant of the jailbreak classifier — **reference/documentation only**.

    NOT used by the server and NOT production-ready: this ONNX export emits an
    uncalibrated decision function (not probabilities), which degrades accuracy and
    skews predictions toward false positives versus the ``snowflake.pkl`` random forest
    served at ``/v1/classify``. It is kept here solely as a reference for the ONNX path.
    ``onnxruntime`` is intentionally **not** a declared dependency — instantiating this
    class will fail until you install it manually to experiment.
    """

    @no_type_check
    def __init__(self, device: str | None = None, embed: SnowflakeEmbed | None = None) -> None:
        from huggingface_hub import hf_hub_download
        from onnxruntime import InferenceSession

        logger.info("Initializing jailbreak classifier (onnxruntime)...")
        self.embed = embed if embed is not None else SnowflakeEmbed(device=device)
        logger.info("Loading random forest %s from %s...", ONNX_FILENAME, MODEL_REPO_ID)
        onnx_path = hf_hub_download(
            repo_id=MODEL_REPO_ID,
            filename=ONNX_FILENAME,
            revision=MODEL_REVISION,
        )
        self.session = InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        logger.info("Jailbreak classifier (onnx) ready.")

    @no_type_check
    def __call__(self, text: str) -> tuple[bool, float]:
        embedding = self.embed(text)
        features = np.asarray([embedding], dtype=np.float32)
        # outputs[0] = output_label; outputs[1] = output_probability (one per-class
        # dict). This export carries decision-function values, not probabilities.
        outputs: Any = self.session.run(None, {"X": features})
        classification = int(np.asarray(outputs[0]).reshape(-1)[0])
        prob = float(outputs[1][0][classification])
        score = -prob if classification == 0 else prob
        return bool(classification), score
