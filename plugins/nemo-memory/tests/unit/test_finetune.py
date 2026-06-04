# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the fine-tune corpus extractor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_memory_plugin.triage.finetune import (
    build_finetune_corpus,
    to_jsonl_chat,
    to_jsonl_raw,
    to_markdown_summary,
    write_finetune_artifacts,
)
from nemo_memory_plugin.triage.judges import _SYSTEM


def _vote(
    *,
    model: str,
    verdict: str,
    quality: float = 0.5,
    necessity: float = 0.5,
    justification: str = "",
    refined_text: str | None = None,
    merge_with: list[str] | None = None,
    raw_response: str | None = None,
) -> dict:
    return {
        "model": model,
        "verdict": verdict,
        "quality": quality,
        "necessity": necessity,
        "justification": justification,
        "refined_text": refined_text,
        "merge_with": merge_with or [],
        "raw_response": raw_response or json.dumps({"verdict": verdict}),
        "elapsed_sec": 1.0,
    }


def _proposal(
    eid: str,
    *,
    aggregate_verdict: str,
    votes: list[dict],
) -> dict:
    judge_votes = {v["model"]: v for v in votes}
    return {
        "entry_id": eid,
        "verdict": aggregate_verdict,
        "quality_score": 0.5,
        "necessity_score": 0.5,
        "confidence": 1.0,
        "judge_votes": judge_votes,
        "justification": "",
        "refined_text": None,
        "merge_with": [],
    }


def _artifact(proposals: list[dict], *, council: list[str], store_name: str = "test-store") -> dict:
    from collections import Counter

    return {
        "store_name": store_name,
        "council_models": council,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "elapsed_sec": 1.0,
        "verdict_counts": dict(Counter(p["verdict"] for p in proposals)),
        "proposals": proposals,
        "errors": [],
        "skipped_entries": [],
    }


def _corpus_with_entries(tmp_path: Path, entries: list[tuple[str, int]]) -> Path:
    """Write a pi-hermes-shaped USER.md whose entries' content matches the
    given (content, corroboration_count) pairs.

    pi-hermes uses `§` separators between entries, with `(seen-in N session(s))`
    markers attached to the entry for corroboration counts.
    """
    parts: list[str] = []
    for content, n in entries:
        block = f"{content}\n\n(seen-in {n} session{'s' if n != 1 else ''})"
        parts.append(block)
    body = "\n\n§\n\n".join(parts) + "\n"
    p = tmp_path / "USER.md"
    p.write_text(body, encoding="utf-8")
    return p


def _write_artifact(tmp_path: Path, artifact: dict, name: str = "triage.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(artifact), encoding="utf-8")
    return p


def _build_pair(
    tmp_path: Path,
    *,
    entry_contents: list[str],
    sonnet_verdicts: list[str],
    nano_verdicts: list[str] | None = None,
) -> tuple[Path, Path, list[str]]:
    """Build a synthetic corpus + matching artifact; return paths + entry IDs.

    The corpus is built first; entry IDs are then computed by loading
    through PiHermesMemoryStore, so the artifact's entry_ids match what
    the live store would produce.
    """
    from nemo_memory_plugin.triage.adapters.pi_hermes import PiHermesMemoryStore

    corpus = _corpus_with_entries(tmp_path, [(c, 1) for c in entry_contents])
    store = PiHermesMemoryStore(path=corpus, name="test-store")
    entries = list(store.list_entries())
    assert len(entries) == len(entry_contents), "corpus parse mismatch — fix the fixture"
    entry_ids = [e.id for e in entries]

    council = ["sonnet"]
    if nano_verdicts is not None:
        council.append("nano")

    proposals = []
    for i, eid in enumerate(entry_ids):
        votes = [_vote(model="sonnet", verdict=sonnet_verdicts[i])]
        if nano_verdicts is not None:
            votes.append(_vote(model="nano", verdict=nano_verdicts[i]))
        proposals.append(_proposal(eid, aggregate_verdict=sonnet_verdicts[i], votes=votes))

    artifact = _artifact(proposals, council=council, store_name="test-store")
    artifact_path = _write_artifact(tmp_path, artifact)
    return artifact_path, corpus, entry_ids


class TestBuildFinetuneCorpus:
    def test_extracts_full_labeled_corpus_with_only_reference(self, tmp_path: Path) -> None:
        # Just a reference judge, no candidate. Every proposal should land
        # in the corpus with is_disagreement=False and candidate=None.
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["entry one content.", "entry two content."],
            sonnet_verdicts=["keep", "promote_to_prompt"],
        )
        records, summary = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")

        assert len(records) == 2
        assert summary.total_records == 2
        assert summary.label_verdict_counts == {"keep": 1, "promote_to_prompt": 1}
        assert summary.disagreement_count == 0
        for r in records:
            assert r.reference_judge == "sonnet"
            assert r.candidate_judge is None
            assert r.is_disagreement is False
            assert r.system_prompt == _SYSTEM

    def test_extracts_disagreement_set_with_candidate_filter(self, tmp_path: Path) -> None:
        # Three entries, two disagree (keep vs refine), one agrees (keep vs keep).
        # only_disagreements=True should land exactly 2 records, both flagged.
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1.", "e2.", "e3."],
            sonnet_verdicts=["keep", "keep", "keep"],
            nano_verdicts=["refine", "keep", "refine"],
        )
        records, summary = build_finetune_corpus(
            artifact,
            corpus,
            reference_judge="sonnet",
            candidate_judge="nano",
            only_disagreements=True,
        )
        assert len(records) == 2
        assert summary.disagreement_count == 2
        for r in records:
            assert r.is_disagreement is True
            assert r.candidate_verdict == "refine"
            assert r.label_verdict == "keep"

    def test_full_corpus_with_candidate_tags_disagreements(self, tmp_path: Path) -> None:
        # only_disagreements=False with a candidate: every record lands,
        # the disagreement ones get is_disagreement=True.
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1.", "e2.", "e3."],
            sonnet_verdicts=["keep", "promote_to_prompt", "refine"],
            nano_verdicts=["refine", "promote_to_prompt", "keep"],
        )
        records, summary = build_finetune_corpus(artifact, corpus, reference_judge="sonnet", candidate_judge="nano")
        assert len(records) == 3
        assert summary.disagreement_count == 2  # e1 + e3 disagree, e2 agrees
        # The two disagreement entries have is_disagreement=True; the
        # agreeing one is False but still has candidate metadata.
        disagree_flags = [r.is_disagreement for r in records]
        assert disagree_flags.count(True) == 2
        assert disagree_flags.count(False) == 1
        for r in records:
            assert r.candidate_judge == "nano"

    def test_only_disagreements_requires_candidate(self, tmp_path: Path) -> None:
        # The filter is meaningless without a candidate; spec must raise
        # rather than silently degrade to "return everything".
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1."],
            sonnet_verdicts=["keep"],
        )
        with pytest.raises(ValueError, match="only_disagreements=True requires"):
            build_finetune_corpus(artifact, corpus, reference_judge="sonnet", only_disagreements=True)

    def test_unknown_reference_judge_raises(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1."],
            sonnet_verdicts=["keep"],
        )
        with pytest.raises(ValueError, match="not in the artifact's council_models"):
            build_finetune_corpus(artifact, corpus, reference_judge="not-a-real-judge")

    def test_unknown_candidate_judge_raises(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1."],
            sonnet_verdicts=["keep"],
            nano_verdicts=["refine"],
        )
        with pytest.raises(ValueError, match="not in the artifact's council_models"):
            build_finetune_corpus(artifact, corpus, reference_judge="sonnet", candidate_judge="not-a-real-candidate")

    def test_artifact_missing_required_keys_raises(self, tmp_path: Path) -> None:
        bad = {"store_name": "x"}  # missing council_models + proposals
        path = _write_artifact(tmp_path, bad, name="bad.json")
        corpus = _corpus_with_entries(tmp_path, [("only entry.", 1)])
        with pytest.raises(ValueError, match="missing required top-level keys"):
            build_finetune_corpus(path, corpus, reference_judge="sonnet")


class TestPromptRendering:
    def test_user_prompt_contains_entry_content_and_corroboration(self, tmp_path: Path) -> None:
        # The chat-format export depends on user_prompt being the EXACT
        # string the live judge saw. Verify the rendered prompt has both
        # the entry text and the corroboration marker.
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["a very specific entry text"],
            sonnet_verdicts=["keep"],
        )
        records, _ = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")
        assert len(records) == 1
        assert "a very specific entry text" in records[0].user_prompt
        assert "corroboration: this entry was observed in 1 independent session" in records[0].user_prompt

    def test_chat_messages_uses_raw_response_when_available(self, tmp_path: Path) -> None:
        # When the judge's raw_response is captured, the assistant turn
        # must be that exact string (not a re-serialized round-trip).
        from nemo_memory_plugin.triage.adapters.pi_hermes import PiHermesMemoryStore

        corpus = _corpus_with_entries(tmp_path, [("e1.", 1)])
        store = PiHermesMemoryStore(path=corpus, name="test-store")
        eid = next(iter(store.list_entries())).id
        custom_raw = '{"verdict": "keep", "quality": 0.95, "necessity": 0.95, "justification": "custom inline raw"}'
        artifact = _artifact(
            [
                _proposal(
                    eid,
                    aggregate_verdict="keep",
                    votes=[_vote(model="sonnet", verdict="keep", raw_response=custom_raw)],
                )
            ],
            council=["sonnet"],
            store_name="test-store",
        )
        ap = _write_artifact(tmp_path, artifact)
        records, _ = build_finetune_corpus(ap, corpus, reference_judge="sonnet")
        messages = records[0].to_chat_messages()
        assert messages[-1] == {"role": "assistant", "content": custom_raw}


class TestSerializers:
    def test_to_jsonl_raw_one_record_per_line(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1.", "e2."],
            sonnet_verdicts=["keep", "drop"],
        )
        records, _ = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")
        jsonl = to_jsonl_raw(records)
        lines = [json.loads(line) for line in jsonl.strip().split("\n")]
        assert len(lines) == 2
        # The label block carries the gold verdict.
        verdicts = sorted(d["label"]["verdict"] for d in lines)
        assert verdicts == ["drop", "keep"]

    def test_to_jsonl_chat_messages_shape(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1."],
            sonnet_verdicts=["keep"],
        )
        records, _ = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")
        jsonl = to_jsonl_chat(records)
        line = json.loads(jsonl.strip())
        assert "messages" in line
        roles = [m["role"] for m in line["messages"]]
        assert roles == ["system", "user", "assistant"]

    def test_to_markdown_summary_renders_label_distribution(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1.", "e2.", "e3."],
            sonnet_verdicts=["keep", "keep", "drop"],
        )
        _records, summary = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")
        md = to_markdown_summary(summary)
        assert "Total records: **3**" in md
        assert "`keep` | 2 |" in md
        assert "`drop` | 1 |" in md


class TestWriteArtifacts:
    def test_writes_three_files(self, tmp_path: Path) -> None:
        artifact, corpus, _ids = _build_pair(
            tmp_path,
            entry_contents=["e1.", "e2."],
            sonnet_verdicts=["keep", "drop"],
        )
        records, summary = build_finetune_corpus(artifact, corpus, reference_judge="sonnet")
        out = tmp_path / "out"
        paths = write_finetune_artifacts(records, summary, out, basename="ft1")
        assert set(paths.keys()) == {"raw", "chat", "summary"}
        for key, p in paths.items():
            assert p.exists(), f"{key} artifact missing"
        assert paths["raw"].name == "ft1.jsonl"
        assert paths["chat"].name == "ft1-chat.jsonl"
        assert paths["summary"].name == "ft1.md"


class TestRealV1ArtifactSmoke:
    """Smoke against the committed v1 Sonnet 4.5 + Nano + Kimi artifact.

    Confirms the extractor handles real artifact JSON without changes and
    that the disagreement count matches the bd ``mdubrinsky-7au.3``
    description (40 entries where Nano disagreed with Sonnet 4.5).
    """

    def test_v1_disagreement_set_has_40_records(self) -> None:
        artifact = Path("plugins/nemo-memory/src/nemo_memory_plugin/triage/phase1-smoke/triage-user.json")
        corpus = Path("~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md").expanduser()
        if not artifact.exists() or not corpus.exists():
            pytest.skip("v1 artifact or PoC corpus not present in this checkout")

        records, summary = build_finetune_corpus(
            artifact,
            corpus,
            reference_judge="azure-anthropic-claude-sonnet-4-5",
            candidate_judge="nvidia-nvidia-nemotron-3-nano-30b-a3b",
            only_disagreements=True,
        )
        assert len(records) == 40, f"Expected 40 disagreement records (per bd mdubrinsky-7au.3); got {len(records)}."
        assert summary.disagreement_count == 40
        # Every record in the only_disagreements view must actually be a
        # disagreement (otherwise the filter is broken).
        assert all(r.is_disagreement for r in records)
