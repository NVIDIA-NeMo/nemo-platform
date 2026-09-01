# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

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
