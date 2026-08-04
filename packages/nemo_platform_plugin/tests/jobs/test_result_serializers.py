# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for job result serializers."""

from __future__ import annotations

import tarfile
from pathlib import Path

from nemo_platform_plugin.jobs.api_factory import FileResultSerializer


def test_file_serializer_serves_a_regular_file_directly(tmp_path: Path) -> None:
    result = tmp_path / "evaluation-results.json"
    result.write_text('{"ok": true}', encoding="utf-8")

    response = FileResultSerializer().serialize(result)

    assert Path(response.path) == result
    assert response.filename == "evaluation-results.json"


def test_file_serializer_serves_the_archive_it_builds_for_a_directory(tmp_path: Path) -> None:
    """A directory result must download as its tarball.

    ``FileResponse`` stats its path and rejects anything that is not a regular file, so returning
    the directory made every directory-valued result (job artifact bundles) undownloadable.
    """
    bundle = tmp_path / "agent-eval-results"
    bundle.mkdir()
    (bundle / "trials.jsonl").write_text('{"id": "t-1"}\n', encoding="utf-8")

    response = FileResultSerializer().serialize(bundle)

    served = Path(response.path)
    assert served.is_file(), "a directory result must be served as a file, not the directory itself"
    assert response.filename == "agent-eval-results.tar.gz"
    with tarfile.open(served) as tar:
        assert "agent-eval-results/trials.jsonl" in tar.getnames()
