# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.values.evidence import (
    CandidateEvidence,
    EvidenceDescriptor,
    LocalFilesystemEvidence,
)


def test_metric_input_preserves_candidate_evidence_out_of_metadata() -> None:
    evidence = CandidateEvidence(
        descriptors={"trace": EvidenceDescriptor(kind="atif", ref="atif://trial-trace#L9", format="atif")}
    )

    metric_input = build_metric_input(
        {"prompt": "Question?"},
        {"output_text": "Answer", "evidence": evidence, "custom": "metadata"},
        index=3,
    )

    assert metric_input.candidate.evidence == evidence
    assert metric_input.candidate.evidence is not None
    assert metric_input.candidate.evidence.require("trace", kind="atif") == evidence.descriptors["trace"]
    assert metric_input.candidate.metadata == {"custom": "metadata"}


@pytest.mark.asyncio
async def test_candidate_evidence_filesystem_access_is_lazy_and_cached(tmp_path: Path) -> None:
    final_state = tmp_path / "final"
    final_state.mkdir()
    (final_state / "answer.txt").write_text("done", encoding="utf-8")
    (final_state / "nested").mkdir()
    (final_state / "nested" / "notes.txt").write_text("notes", encoding="utf-8")

    evidence = CandidateEvidence(
        descriptors={
            "remote_state": EvidenceDescriptor(kind="filesystem", ref="https://example.test/archive.tgz"),
            "final_state": EvidenceDescriptor(kind="filesystem", ref=str(final_state)),
        }
    )

    assert evidence.require("remote_state", kind="filesystem").ref == "https://example.test/archive.tgz"

    handle = await evidence.filesystem("final_state")
    cached = await evidence.filesystem("final_state")

    assert handle is cached
    assert await handle.exists("answer.txt") is True
    assert await handle.read_text("answer.txt") == "done"
    assert await handle.iter_paths(recursive=True) == ["answer.txt", "nested", "nested/notes.txt"]
    with pytest.raises(ValueError, match="outside evidence root"):
        handle.path("../outside")
    with pytest.raises(ValueError, match="only supports local filesystem"):
        await evidence.filesystem("remote_state")


@pytest.mark.asyncio
async def test_filesystem_read_bytes_list_and_diff(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    for root in (before, after):
        (root / "src").mkdir(parents=True)
    (before / "keep.txt").write_text("same", encoding="utf-8")
    (before / "src" / "mod.py").write_text("old", encoding="utf-8")
    (before / "gone.txt").write_text("bye", encoding="utf-8")
    (after / "keep.txt").write_text("same", encoding="utf-8")
    (after / "src" / "mod.py").write_text("new", encoding="utf-8")
    (after / "added.txt").write_text("hi", encoding="utf-8")

    initial = LocalFilesystemEvidence(before)
    final = LocalFilesystemEvidence(after)

    assert await final.read_bytes("added.txt") == b"hi"
    assert await final.list_files("**/*.py") == ["src/mod.py"]

    diff = await initial.diff(final)
    assert {(entry.path, entry.change_type) for entry in diff.entries} == {
        ("added.txt", "added"),
        ("gone.txt", "deleted"),
        ("src/mod.py", "modified"),
    }
    assert [entry.path for entry in diff.changed(prefix="src/", kinds={"modified"})] == ["src/mod.py"]


@pytest.mark.asyncio
async def test_run_verifier_uses_overlay_and_reports_outcome(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "answer.txt").write_text("42", encoding="utf-8")
    handle = LocalFilesystemEvidence(root)

    ok = await handle.run_verifier(["cat", "answer.txt"])
    assert ok.ok and ok.exit_code == 0 and ok.stdout.strip() == "42"

    failed = await handle.run_verifier(["false"])
    assert not failed.ok and failed.exit_code != 0

    timed_out = await handle.run_verifier(["sleep", "5"], timeout_s=0.2)
    assert timed_out.timed_out and not timed_out.ok

    # The verifier ran in a throwaway copy, so the stored evidence is untouched.
    await handle.run_verifier(["sh", "-c", "echo cheat > sneaked.txt"])
    assert await handle.list_files("**/*") == ["answer.txt"]
