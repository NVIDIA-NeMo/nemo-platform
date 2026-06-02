# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoGuard JailbreakDetect model.

A two-stage pipeline, ported from the ``nemoguardrails`` library
(``library/jailbreak_detection/model_based/models.py``) so it can be served
independently of the NVIDIA NIM.

Stage 1 — ``SnowflakeEmbed``: the ``Snowflake/snowflake-arctic-embed-m-long``
transformer encoder, used as a frozen feature extractor. The CLS-token
embedding is taken (``model(**tokens)[0][:, 0]``), matching the upstream
implementation.

Stage 2 — ``JailbreakClassifier``: a scikit-learn random forest exported to
ONNX (``snowflake.onnx`` from the gated ``nvidia/NemoGuard-JailbreakDetect``
Hugging Face repo), run on CPU through ``onnxruntime``.

This module has no dependency on ``nemo_platform`` so the model container stays
lean; it is imported by both the standalone server (``server.py``) and the tests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

import numpy as np

logger = logging.getLogger(__name__)

SNOWFLAKE_MODEL_ID = "Snowflake/snowflake-arctic-embed-m-long"
MODEL_FILENAME = "snowflake.onnx"
MODEL_REPO_ID = "nvidia/NemoGuard-JailbreakDetect"

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
            trust_remote_code=True,
        )
        self.model = AutoModel.from_pretrained(
            SNOWFLAKE_MODEL_ID,
            trust_remote_code=True,
            add_pooling_layer=False,
            use_safetensors=True,
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
    """Embedding + ONNX random-forest jailbreak classifier.

    Calling the instance with a prompt returns ``(is_jailbreak, score)`` where
    ``score`` follows the upstream signed-probability convention: negative when
    the prompt is classified safe, positive when classified as a jailbreak.
    """

    def __init__(self, random_forest_path: str, device: str | None = None) -> None:
        from onnxruntime import InferenceSession

        self.embed = SnowflakeEmbed(device=device)
        # The random forest is tiny; CPU inference is the right call even when
        # the embedder runs on GPU.
        self.classifier = InferenceSession(random_forest_path, providers=["CPUExecutionProvider"])

    def __call__(self, text: str) -> tuple[bool, float]:
        embedding = self.embed(text)
        features = np.asarray([embedding], dtype=np.float32)
        # onnxruntime types `run` as a broad union; the RF returns a label array
        # plus a per-class probability mapping. Cast to keep type-checkers happy.
        outputs = cast(list[Any], self.classifier.run(None, {"X": features}))
        classification = int(np.asarray(outputs[0]).reshape(-1)[0])
        # outputs[1] is a list of per-class probability dicts; one element here.
        prob = float(outputs[1][0][classification])
        score = -prob if classification == 0 else prob
        return bool(classification), float(score)


def ensure_model_downloaded(classifier_dir: str) -> Path:
    """Ensure ``snowflake.onnx`` exists locally, downloading it if needed.

    Mirrors the upstream loader: honours a pre-populated directory (e.g. baked
    into the container image) and only reaches Hugging Face when the file is
    absent.
    """
    directory = Path(classifier_dir)
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / MODEL_FILENAME

    if not model_path.is_file():
        from huggingface_hub import hf_hub_download

        logger.info("Downloading %s from %s", MODEL_FILENAME, MODEL_REPO_ID)
        hf_hub_download(
            repo_id=MODEL_REPO_ID,
            filename=MODEL_FILENAME,
            local_dir=classifier_dir,
        )

    return model_path


def load_classifier(classifier_dir: str | None = None, device: str | None = None) -> JailbreakClassifier:
    """Build a :class:`JailbreakClassifier`, downloading the RF if necessary.

    ``classifier_dir`` defaults to the ``EMBEDDING_CLASSIFIER_PATH`` environment
    variable, matching the upstream contract and the container image layout.
    """
    if classifier_dir is None:
        classifier_dir = os.environ.get("EMBEDDING_CLASSIFIER_PATH")
    if not classifier_dir:
        raise RuntimeError(
            "No classifier path provided. Set EMBEDDING_CLASSIFIER_PATH or pass classifier_dir explicitly."
        )
    model_path = ensure_model_downloaded(classifier_dir)
    return JailbreakClassifier(str(model_path), device=device)
