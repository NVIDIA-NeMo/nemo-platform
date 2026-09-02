# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest
from nemo_data_designer_plugin.retrieval.corpus import _download_fileset, materialize_corpus
from nemo_data_designer_plugin.retrieval.manifest import resolve_generation_input


def test_fileset_corpus_must_match_job_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not match job workspace"):
        _download_fileset(
            "other/documents",
            dest=tmp_path / "corpus",
            sdk=Mock(),
            workspace="default",
        )


def test_local_corpus_path_is_preview_only(tmp_path: Path) -> None:
    corpus = tmp_path / "documents"
    corpus.mkdir()

    assert (
        materialize_corpus(
            str(corpus),
            dest=tmp_path / "unused",
            sdk=Mock(),
            workspace="default",
            allow_local_path=True,
        )
        == corpus.resolve()
    )

    with pytest.raises(ValueError):
        materialize_corpus(
            str(corpus),
            dest=tmp_path / "unused",
            sdk=Mock(),
            workspace="default",
        )


def test_generation_manifest_rejects_non_object_json(tmp_path: Path) -> None:
    manifest = tmp_path / "generation_result.json"
    manifest.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid generation manifest"):
        resolve_generation_input(manifest)


@pytest.mark.parametrize(
    "corpus",
    [
        "hf://org/dataset/../../sibling",
        "hf://org/dataset//sibling",
    ],
)
def test_hf_corpus_rejects_path_traversal(tmp_path: Path, corpus: str) -> None:
    with pytest.raises(ValueError, match="subdirectory"):
        materialize_corpus(
            corpus,
            dest=tmp_path / "corpus",
            sdk=Mock(),
            workspace="default",
        )


def test_hf_corpus_requires_retrieval_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    with pytest.raises(ImportError, match=r"nemo-data-designer-plugin\[retrieval-sdg\]"):
        materialize_corpus(
            "hf://org/dataset",
            dest=tmp_path / "corpus",
            sdk=Mock(),
            workspace="default",
        )


def test_generation_and_preview_require_retrieval_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "data_designer_retrieval_sdg", types.ModuleType("data_designer_retrieval_sdg"))
    from nemo_data_designer_plugin.retrieval.generation import execute_generation

    with pytest.raises(ImportError, match=r"Retrieval generate and preview requires"):
        execute_generation(Mock(), preview=True)
