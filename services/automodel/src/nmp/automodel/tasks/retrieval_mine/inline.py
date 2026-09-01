# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Convert wrapped Automodel retrieval JSON into inline JSONL for Customizer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def wrapped_to_inline_jsonl(train_json: Path, output_jsonl: Path, corpus_parquet: Path | None = None) -> Path:
    """Emit ``{query, pos_doc, neg_doc}`` JSONL from wrapped Automodel JSON."""
    payload = json.loads(train_json.read_text(encoding="utf-8"))
    records = payload.get("data", [])
    corpus_by_id = _load_corpus(train_json, corpus_parquet)

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            pos_texts = [_doc_text(doc, corpus_by_id) for doc in record.get("pos_doc", [])]
            neg_texts = [_doc_text(doc, corpus_by_id) for doc in record.get("neg_doc", [])]
            for pos_doc in pos_texts or [""]:
                handle.write(
                    json.dumps(
                        {
                            "query": record.get("question", ""),
                            "pos_doc": pos_doc,
                            "neg_doc": neg_texts,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    return output_jsonl


def _load_corpus(train_json: Path, corpus_parquet: Path | None) -> dict[str, str]:
    parquet_path = corpus_parquet or train_json.parent / "corpus" / "train.parquet"
    if not parquet_path.exists() or parquet_path.suffix != ".parquet":
        return {}
    frame = pd.read_parquet(parquet_path)
    id_col = "id" if "id" in frame.columns else frame.columns[0]
    text_col = "text" if "text" in frame.columns else ("contents" if "contents" in frame.columns else None)
    if text_col is None:
        return {}
    return {str(row[id_col]): str(row[text_col]) for _, row in frame.iterrows()}


def _doc_text(doc: Any, corpus_by_id: dict[str, str]) -> str:
    if isinstance(doc, str):
        return doc
    if isinstance(doc, dict):
        if "text" in doc:
            return str(doc["text"])
        if "contents" in doc:
            return str(doc["contents"])
        doc_id = doc.get("id")
        if doc_id is not None:
            return corpus_by_id.get(str(doc_id), str(doc_id))
    return str(doc)
