# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Gym runner: content-hash identity, instruction rendering, task
discovery, and the rollout→trial fan-out — verified against a captured mcqa bundle.

Gym mutates ``responses_create_params`` and copies only a fixed allowlist of row
keys onto results, so ``_ng_task_index`` is the only surviving join. The runner
*assigns* that index in a materialized dataset rather than inferring it; these
tests lock that behaviour in (including against the real captured output)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections import Counter, deque
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime import (
    _LOG_TAIL_LINES,
    NG_ROLLOUT_INDEX,
    NG_TASK_INDEX,
    GymAgentTaskRunner,
    GymRewardMetric,
    GymRuntimeConfig,
    _aggregate_metrics_path_for,
    _canonical_row_hash,
    _content_text,
    _drain_pumps,
    _ensure_fresh_output,
    _flatten_overrides,
    _gym_executable,
    _hydra_scalar,
    _materialize_dataset,
    _pump_stream,
    _read_run_aggregations,
    _render_instruction,
    _require_full_coverage,
    _selection_args,
    _source_datasets,
    _trials_from_rollouts,
    discover_gym_tasks,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus
from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = FIXTURES / "gym_mcqa_example.jsonl"
ROLLOUTS = FIXTURES / "gym_mcqa_rollouts.jsonl"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _index_map(tasks: list, tmp_path: Path) -> tuple[list[str], dict[int, str]]:
    """Materialize ``tasks`` the way the runner does, returning (task ids in order, index->id map)."""
    index_map = _materialize_dataset(tasks, tmp_path / "gym_input.jsonl")
    return [task.id for task in tasks], index_map


def test_canonical_row_hash_is_stable_and_ignores_runtime_fields() -> None:
    base = {"responses_create_params": {"input": "q"}, "expected_answer": "A"}
    digest = _canonical_row_hash(base)
    # runtime-injected index fields do not perturb the hash
    assert _canonical_row_hash({**base, "_ng_task_index": 3, "_ng_rollout_index": 1}) == digest
    # key order does not matter
    assert _canonical_row_hash({"expected_answer": "A", "responses_create_params": {"input": "q"}}) == digest
    # a real content change yields a new id
    assert _canonical_row_hash({**base, "expected_answer": "B"}) != digest


def test_render_instruction_from_string_messages_and_parts() -> None:
    assert _render_instruction({"input": "hello"}) == "hello"
    assert _render_instruction({"input": [{"role": "user", "content": "pick A or B"}]}) == "pick A or B"
    assert _render_instruction({"instructions": "be brief", "input": "q"}) == "be brief\n\nq"
    parts = {"input": [{"role": "user", "content": [{"type": "input_text", "text": "part"}]}]}
    assert _render_instruction(parts) == "part"


def test_render_instruction_fails_loudly_when_empty() -> None:
    with pytest.raises(ValueError):
        _render_instruction({"input": ""})
    with pytest.raises(ValueError):
        _render_instruction({})


def test_discover_gym_tasks_from_example_fixture() -> None:
    tasks = discover_gym_tasks(EXAMPLE)
    assert len(tasks) == len(_rows(EXAMPLE))
    assert len({task.id for task in tasks}) == len(tasks)  # unique ids
    for task in tasks:
        assert len(task.id) == 64  # sha256 hex
        assert task.inputs["instruction"]  # non-empty instruction
        assert task.metadata["gym_dataset_path"].endswith("gym_mcqa_example.jsonl")
        assert [type(metric).__name__ for metric in task.metrics] == ["GymRewardMetric"]


def test_materialize_dataset_stamps_task_index_and_returns_total_map(tmp_path: Path) -> None:
    # The runner assigns _ng_task_index rather than inferring it: every task gets exactly one row,
    # stamped with its own index, and the returned map covers all of them.
    tasks = discover_gym_tasks(EXAMPLE)
    dest = tmp_path / "gym_input.jsonl"
    index_map = _materialize_dataset(tasks, dest)
    rows = _rows(dest)
    assert len(rows) == len(tasks)
    assert [row[NG_TASK_INDEX] for row in rows] == list(range(len(tasks)))
    assert index_map == {index: task.id for index, task in enumerate(tasks)}
    # the full source row is carried through so Gym's verifier still sees its non-prompt fields
    assert all("responses_create_params" in row for row in rows)
    # Gym assigns the rollout index per attempt; ours must not be present to be honored/overridden
    assert all(NG_ROLLOUT_INDEX not in row for row in rows)


def test_materialize_dataset_subsets_to_requested_tasks(tmp_path: Path) -> None:
    # Running a subset must hand Gym only that subset — otherwise Gym rolls out (and bills for) rows
    # whose trials we would then discard.
    tasks = discover_gym_tasks(EXAMPLE)
    subset = [tasks[3], tasks[1]]
    index_map = _materialize_dataset(subset, tmp_path / "gym_input.jsonl")
    assert index_map == {0: tasks[3].id, 1: tasks[1].id}
    assert len(_rows(tmp_path / "gym_input.jsonl")) == 2


def test_materialize_dataset_overrides_preassigned_task_index(tmp_path: Path) -> None:
    # Codex's example 1: a dataset that already carries out-of-order _ng_task_index values. Gym honors
    # a pre-stamped index, so leaving the source values in place would swap trials between tasks. Our
    # stamp must be authoritative, and the map must agree with it.
    dataset = tmp_path / "preindexed.jsonl"
    dataset.write_text(
        json.dumps({NG_TASK_INDEX: 1, "responses_create_params": {"input": "What is 2 + 2?"}})
        + "\n"
        + json.dumps({NG_TASK_INDEX: 0, "responses_create_params": {"input": "What is France's capital?"}})
        + "\n",
        encoding="utf-8",
    )
    tasks = discover_gym_tasks(dataset)
    index_map = _materialize_dataset(tasks, tmp_path / "gym_input.jsonl")
    rows = _rows(tmp_path / "gym_input.jsonl")
    assert [row[NG_TASK_INDEX] for row in rows] == [0, 1]  # source values discarded
    # index 0 is the math row (first in file order), index 1 the capital row
    assert "2 + 2" in json.dumps(rows[0]["responses_create_params"])
    assert index_map[0] == tasks[0].id and index_map[1] == tasks[1].id

    # ...and the join round-trips: Gym echoing our stamps attributes each rollout to the right task.
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(
        json.dumps({NG_TASK_INDEX: 1, NG_ROLLOUT_INDEX: 0, "response": "Lyon", "reward": 0.0})
        + "\n"
        + json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "response": "4", "reward": 1.0})
        + "\n",
        encoding="utf-8",
    )
    trials = _trials_from_rollouts(bundle, tasks, index_map)
    responses = {trial.task_id: (trial.output.response if trial.output else None) for trial in trials}
    rewards = {trial.task_id: trial.metadata["reward"] for trial in trials}
    assert responses[tasks[0].id] == "4"  # the math task got the math answer, not the capital task's
    assert rewards[tasks[0].id] == 1.0
    assert responses[tasks[1].id] == "Lyon"


def test_serialization_variant_rows_collapse_without_index_drift(tmp_path: Path) -> None:
    # Codex's example 2: two rows with identical JSON *values* but different serialization. Gym's own
    # fallback dedup keys off raw line text and would assign two indices; ours collapses them to one
    # task. Because we now stamp the index ourselves, Gym never gets the chance to disagree.
    dataset = tmp_path / "variants.jsonl"
    dataset.write_text(
        '{"responses_create_params":{"input":"Choose A"},"expected":"A"}\n'
        '{ "expected": "A", "responses_create_params": { "input": "Choose A" } }\n',
        encoding="utf-8",
    )
    tasks = discover_gym_tasks(dataset)
    assert len(tasks) == 1  # same content -> same task
    index_map = _materialize_dataset(tasks, tmp_path / "gym_input.jsonl")
    assert index_map == {0: tasks[0].id}
    assert len(_rows(tmp_path / "gym_input.jsonl")) == 1  # Gym is handed one row, so it emits one index


def test_discover_gym_tasks_warns_on_duplicate_rows(tmp_path: Path, caplog) -> None:
    # Repeated attempts are num_repeats, not row duplication. Duplicates collapse (identity is content)
    # and must be reported rather than silently swallowed.
    dataset = tmp_path / "dupes.jsonl"
    row = json.dumps({"responses_create_params": {"input": "same question"}})
    dataset.write_text(row + "\n" + row + "\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        tasks = discover_gym_tasks(dataset)
    assert len(tasks) == 1
    assert "duplicate row" in caplog.text
    assert "num_repeats" in caplog.text


def test_materialize_dataset_reports_empty_task_list(tmp_path: Path) -> None:
    # The empty case used to surface as a confusing "needs a dataset path" from the provenance helper.
    with pytest.raises(ValueError, match="no tasks to run"):
        _materialize_dataset([], tmp_path / "gym_input.jsonl")


def test_materialize_dataset_rejects_duplicate_tasks(tmp_path: Path) -> None:
    tasks = discover_gym_tasks(EXAMPLE)
    with pytest.raises(ValueError, match="more than once"):
        _materialize_dataset([tasks[0], tasks[0]], tmp_path / "gym_input.jsonl")


def test_materialize_dataset_requires_source_rows(tmp_path: Path) -> None:
    # Tasks not built by discover_gym_tasks can't be re-materialized; fail before launching Gym.
    tasks = discover_gym_tasks(EXAMPLE)
    no_extras = tasks[0].model_copy(update={"metadata": {"gym_dataset_path": str(EXAMPLE)}})
    with pytest.raises(ValueError, match="gym_row_extras"):
        _materialize_dataset([no_extras], tmp_path / "gym_input.jsonl")
    # the other half of the split is equally required
    no_params = tasks[0].model_copy(update={"inputs": {"instruction": tasks[0].inputs["instruction"]}})
    with pytest.raises(ValueError, match="gym_row"):
        _materialize_dataset([no_params], tmp_path / "gym_input.jsonl")


def test_content_text_warns_on_unsupported_shape(caplog) -> None:
    # A populated content in an unexpected shape means prompt text is being dropped -> warn.
    with caplog.at_level(logging.WARNING):
        assert _content_text({"unexpected": "mapping"}) == ""
    assert "unsupported type" in caplog.text
    # a missing content is unremarkable and must stay quiet
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        assert _content_text(None) == ""
    assert caplog.text == ""


def test_trials_fan_out_one_per_attempt(tmp_path: Path) -> None:
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    # synthesize a bundle: the first 2 tasks (indices 0,1) x 2 attempts, joined via _ng_task_index
    records = [
        {NG_TASK_INDEX: index, NG_ROLLOUT_INDEX: attempt, "reward": float(attempt), "response": {"ok": True}}
        for index in (0, 1)
        for attempt in range(2)  # num_repeats = 2
    ]
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    trials = _trials_from_rollouts(bundle, tasks, index_map)
    assert len(trials) == 4  # 2 tasks x 2 attempts
    assert len({trial.id for trial in trials}) == 4  # distinct trial ids
    assert {trial.task_id for trial in trials} == {ordered[0], ordered[1]}  # attributed via _ng_task_index
    assert set(Counter(trial.task_id for trial in trials).values()) == {2}  # 2 trials per task
    assert {trial.metadata["reward"] for trial in trials} == {0.0, 1.0}


def test_trials_raise_on_unstamped_task_index(tmp_path: Path) -> None:
    # Every row Gym read carried an index we stamped, so an index we never issued means Gym reassigned
    # them instead of honoring ours. Attributing it would be a silent mis-join -> fail loudly.
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 999, "reward": 1.0}) + "\n", encoding="utf-8")  # out of range
    with pytest.raises(ValueError):
        _trials_from_rollouts(bundle, tasks, index_map)


def test_failures_sidecar_yields_failed_trials(tmp_path: Path) -> None:
    # Gym writes failed attempts to a *_failures.jsonl sidecar, not rollouts.jsonl. They must surface
    # as FAILED trials (counted + diagnosed), not vanish.
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": 1.0}) + "\n", encoding="utf-8")
    failures = tmp_path / "rollouts_failures.jsonl"
    failures.write_text(json.dumps({NG_TASK_INDEX: 1, NG_ROLLOUT_INDEX: 0, "error": "boom"}) + "\n", encoding="utf-8")
    trials = _trials_from_rollouts(bundle, tasks, index_map)
    by_status = {trial.task_id: trial.status for trial in trials}
    assert by_status[ordered[0]] == AgentEvalTrialStatus.COMPLETED
    assert by_status[ordered[1]] == AgentEvalTrialStatus.FAILED
    failed = next(trial for trial in trials if trial.status == AgentEvalTrialStatus.FAILED)
    assert failed.metadata["reward"] is None
    assert failed.metadata["gym_failure"] == "boom"


def test_ensure_fresh_output_rejects_reused_dir(tmp_path: Path) -> None:
    # Gym appends to the failures sidecar, so a directory already holding one must be refused
    # (rather than cleared) to avoid mixing runs / clobbering prior results.
    rollouts = tmp_path / "rollouts.jsonl"
    (tmp_path / "rollouts_failures.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _ensure_fresh_output(rollouts)


def test_ensure_fresh_output_allows_clean_dir(tmp_path: Path) -> None:
    _ensure_fresh_output(tmp_path / "rollouts.jsonl")  # no prior artifacts -> no raise


def test_source_datasets_is_provenance_only_and_never_raises() -> None:
    # The dataset path no longer drives execution — Gym reads the materialized file, built from the
    # tasks themselves. So mixing datasets in one run is now legitimate (the materialized dataset is
    # the union) and this summary must not gate the run; it only labels a log line.
    tasks = discover_gym_tasks(EXAMPLE)
    assert "gym_mcqa_example.jsonl" in _source_datasets(tasks)
    other = tasks[0].model_copy(update={"metadata": {**tasks[0].metadata, "gym_dataset_path": "/other/ds.jsonl"}})
    summary = _source_datasets([*tasks, other])  # must not raise
    assert "gym_mcqa_example.jsonl" in summary and "/other/ds.jsonl" in summary
    # tasks with no stamped path at all are fine too — the run does not depend on it
    unstamped = tasks[0].model_copy(
        update={"metadata": {k: v for k, v in tasks[0].metadata.items() if k != "gym_dataset_path"}}
    )
    assert _source_datasets([unstamped])


def test_materialize_dataset_reassembles_row_without_storing_params_twice(tmp_path: Path) -> None:
    # The task already carries responses_create_params under inputs['gym_row']; metadata must hold only
    # the *rest* of the row so the run bundle does not persist the same payload twice per task.
    tasks = discover_gym_tasks(EXAMPLE)
    extras = tasks[0].metadata["gym_row_extras"]
    assert "responses_create_params" not in extras  # not duplicated
    # ...yet materialization still reconstructs the complete source row Gym's verifier needs
    _materialize_dataset(tasks, tmp_path / "gym_input.jsonl")
    row = _rows(tmp_path / "gym_input.jsonl")[0]
    source = _rows(EXAMPLE)[0]
    assert {k: v for k, v in row.items() if k != NG_TASK_INDEX} == source


def test_success_records_without_rollout_index_get_distinct_ids(tmp_path: Path) -> None:
    # Mirror of the failure-path guard: two successful attempts for one task lacking _ng_rollout_index
    # must not collapse to a single trial id.
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(
        json.dumps({NG_TASK_INDEX: 0, "reward": 1.0}) + "\n" + json.dumps({NG_TASK_INDEX: 0, "reward": 0.0}) + "\n",
        encoding="utf-8",
    )
    trials = _trials_from_rollouts(bundle, tasks, index_map)
    assert len(trials) == 2
    assert len({trial.id for trial in trials}) == 2  # distinct ids despite missing rollout index
    assert all(trial.task_id == ordered[0] for trial in trials)


def test_indexless_failures_get_distinct_trial_ids(tmp_path: Path) -> None:
    # Kill-shaped failures can lack _ng_rollout_index; two for one task must not collapse to one id.
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text("", encoding="utf-8")  # no successes
    failures = tmp_path / "rollouts_failures.jsonl"
    failures.write_text(
        json.dumps({NG_TASK_INDEX: 1, "error": "oom"})
        + "\n"
        + json.dumps({NG_TASK_INDEX: 1, "error": "sigterm"})
        + "\n",
        encoding="utf-8",
    )
    trials = _trials_from_rollouts(bundle, tasks, index_map)
    assert len(trials) == 2
    assert len({trial.id for trial in trials}) == 2  # distinct ids despite missing rollout index
    assert all(trial.status == AgentEvalTrialStatus.FAILED for trial in trials)
    assert all(trial.task_id == ordered[1] for trial in trials)


def test_malformed_line_in_failures_sidecar_is_skipped(tmp_path: Path) -> None:
    # A truncated line in the abnormal-termination sidecar must not sink the good trials.
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": 1.0}) + "\n", encoding="utf-8")
    failures = tmp_path / "rollouts_failures.jsonl"
    failures.write_text(
        json.dumps({NG_TASK_INDEX: 1, NG_ROLLOUT_INDEX: 0, "error": "boom"}) + "\n{ truncated\n", encoding="utf-8"
    )
    trials = _trials_from_rollouts(bundle, tasks, index_map)  # must not raise
    statuses = Counter(trial.status for trial in trials)
    assert statuses[AgentEvalTrialStatus.COMPLETED] == 1
    assert statuses[AgentEvalTrialStatus.FAILED] == 1  # the valid failure survived; the bad line was skipped


def test_malformed_reward_is_recorded_unscored_not_crashing(tmp_path: Path) -> None:
    # A non-numeric reward must not sink the whole batch; the trial is recorded PARTIAL / unscored.
    tasks = discover_gym_tasks(EXAMPLE)
    ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(
        json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": "not-a-number"}) + "\n", encoding="utf-8"
    )
    trials = _trials_from_rollouts(bundle, tasks, index_map)
    assert len(trials) == 1
    assert trials[0].status == AgentEvalTrialStatus.PARTIAL
    assert trials[0].metadata["reward"] is None


def test_trials_from_real_captured_bundle(tmp_path: Path) -> None:
    # End-to-end join against the real mcqa rollout bundle (--limit 2 --num-repeats 2 → 4 records).
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    trials = _trials_from_rollouts(ROLLOUTS, tasks, index_map)
    records = _rows(ROLLOUTS)
    assert len(trials) == len(records)  # one trial per rollout record
    assert set(Counter(trial.task_id for trial in trials).values()) == {2}  # 2 attempts per task
    assert all(trial.task_id in {task.id for task in tasks} for trial in trials)
    assert all(trial.metadata["reward"] is not None for trial in trials)  # rewards surfaced


@pytest.mark.asyncio
async def test_pump_stream_writes_file_and_mirrors_to_logger(tmp_path: Path, caplog) -> None:
    # Subprocess output must land on disk in full (the durable record) while the logger mirror lets a
    # caller surface it in their terminal through ordinary logging config. Chunked reads mean a line
    # split across reads must still be emitted once, whole.
    stream = asyncio.StreamReader()
    stream.feed_data(b"first line\nsecond ")
    stream.feed_data(b"line\nno trailing newline")
    stream.feed_eof()
    log_path = tmp_path / "gym_eval.stdout.log"
    tails: dict[str, deque] = {}
    with caplog.at_level(logging.DEBUG, logger="nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime"):
        await _pump_stream(stream, log_path, label="gym eval", tails=tails, key="stdout")
    assert log_path.read_text(encoding="utf-8") == "first line\nsecond line\nno trailing newline"
    assert list(tails["stdout"]) == ["first line", "second line", "no trailing newline"]
    assert "second line" in caplog.text  # mirrored at DEBUG, not printed unconditionally


@pytest.mark.asyncio
async def test_pump_stream_tail_is_bounded(tmp_path: Path) -> None:
    # The in-memory tail exists only to enrich a failure message; the file is the complete record, so
    # a long collection must not accumulate its whole transcript in memory.
    stream = asyncio.StreamReader()
    stream.feed_data(b"".join(f"line {n}\n".encode() for n in range(_LOG_TAIL_LINES * 3)))
    stream.feed_eof()
    tails: dict[str, deque] = {}
    await _pump_stream(stream, tmp_path / "out.log", label="gym eval", tails=tails, key="stdout")
    assert len(tails["stdout"]) == _LOG_TAIL_LINES
    assert tails["stdout"][-1] == f"line {_LOG_TAIL_LINES * 3 - 1}"  # kept the *last* lines
    assert len((tmp_path / "out.log").read_text(encoding="utf-8").splitlines()) == _LOG_TAIL_LINES * 3


@pytest.mark.asyncio
async def test_drain_pumps_returns_when_pipe_never_reaches_eof(tmp_path: Path, caplog) -> None:
    # A pump ends only at pipe EOF, which needs every inheritor of the write end to close it. Ray
    # daemonizes gcs_server outside our process group (see _terminate), so a survivor can hold the fd
    # open forever. Draining must therefore be bounded: teardown cannot block on a leaked grandchild.
    stream = asyncio.StreamReader()
    stream.feed_data(b"partial output\n")  # data, but deliberately no feed_eof()
    pump = asyncio.create_task(_pump_stream(stream, tmp_path / "stuck.log", label="gym env start"))
    await asyncio.sleep(0)  # let the pump consume what's buffered and block on the next read

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(_drain_pumps([pump], grace_s=0.05, what="gym env start"), timeout=5)

    assert pump.cancelled() or pump.done()  # abandoned, not awaited forever
    assert "did not finish" in caplog.text  # and the truncation is reported, not silent
    # whatever was read before the stall is still on disk — the file is not lost
    assert "partial output" in (tmp_path / "stuck.log").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_drain_pumps_awaits_normal_completion(tmp_path: Path, caplog) -> None:
    # The bounded drain must not truncate the common case: a pump that reaches EOF is awaited to
    # completion and produces no warning.
    stream = asyncio.StreamReader()
    stream.feed_data(b"all of it\n")
    stream.feed_eof()
    tails: dict[str, deque] = {}
    pump = asyncio.create_task(_pump_stream(stream, tmp_path / "done.log", label="gym eval", tails=tails))
    with caplog.at_level(logging.WARNING):
        await _drain_pumps([pump], grace_s=5, what="gym eval")
    assert pump.done() and not pump.cancelled()
    assert list(tails["stdout"]) == ["all of it"]
    assert "did not finish" not in caplog.text


def test_trials_reject_index_map_disagreeing_with_tasks(tmp_path: Path) -> None:
    # Defence in depth: the index map and the task list must describe the same run. If they diverge,
    # trials would be attributed to tasks the caller never asked to score. People make optimization
    # decisions from these numbers, so a disagreement is a hard error, never a best-effort join.
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": 1.0}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        _trials_from_rollouts(bundle, tasks[1:], index_map)  # map covers a task not in the list


def test_success_record_without_usable_index_is_counted_not_silently_dropped(tmp_path: Path, caplog) -> None:
    # A success record with no usable _ng_task_index can't be attributed, but dropping it silently is
    # the dangerous case: with num_repeats > 1 the task keeps its other trials, so _require_full_coverage
    # won't fire and the task is simply scored on fewer attempts than were actually run. Count + warn,
    # matching what the failures loop already does.
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(
        json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": 1.0})
        + "\n"
        + json.dumps({NG_ROLLOUT_INDEX: 1, "reward": 0.0})  # no _ng_task_index at all
        + "\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        trials = _trials_from_rollouts(bundle, tasks, index_map)
    assert len(trials) == 1  # the unattributable record is still skipped
    assert "1 Gym rollout record(s)" in caplog.text  # ...but reported, with the count
    assert NG_TASK_INDEX in caplog.text
    assert str(bundle) in caplog.text


def test_odd_sidecar_index_is_counted_not_fatal(tmp_path: Path) -> None:
    # The failures sidecar is read tolerantly on purpose: it is written during abnormal termination,
    # so one odd record must not discard every already-parsed success. An unknown index there is
    # unattributable, not evidence of a bad join — and it cannot inflate a score, since failures carry
    # no reward and any task left with no trial still trips _require_full_coverage.
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 0, NG_ROLLOUT_INDEX: 0, "reward": 1.0}) + "\n", encoding="utf-8")
    failures = tmp_path / "rollouts_failures.jsonl"
    failures.write_text(json.dumps({NG_TASK_INDEX: 999, "error": "boom"}) + "\n", encoding="utf-8")

    trials = _trials_from_rollouts(bundle, tasks, index_map)  # must not raise
    assert len(trials) == 1  # the good success survived
    assert trials[0].task_id == tasks[0].id


def test_odd_success_index_still_raises(tmp_path: Path) -> None:
    # The mirror of the above: in the *successes* file an unknown index means Gym reindexed the
    # dataset, so every reward attribution is suspect. That must stay fatal.
    tasks = discover_gym_tasks(EXAMPLE)
    _ordered, index_map = _index_map(tasks, tmp_path)
    bundle = tmp_path / "rollouts.jsonl"
    bundle.write_text(json.dumps({NG_TASK_INDEX: 999, NG_ROLLOUT_INDEX: 0, "reward": 1.0}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not one of"):
        _trials_from_rollouts(bundle, tasks, index_map)


def test_incomplete_collection_raises_with_pointers_to_the_evidence(tmp_path: Path) -> None:
    # AgentEvaluator already hard-fails on a task with no trial (evaluator._score_trials), deliberately:
    # an incomplete run must not read as a successful one with lower counts. Synthesizing FAILED trials
    # here would defeat that guard *and* skew the mean, since an unscored trial is excluded from it.
    # So keep failing — but fail from the runner, naming the evidence, instead of leaving the operator
    # with the evaluator's bare task-id list after paying the full collection cost.
    tasks = discover_gym_tasks(EXAMPLE)
    rollouts = tmp_path / "rollouts.jsonl"
    covered = [trial_task_id for trial_task_id in [tasks[0].id]]
    with pytest.raises(RuntimeError) as excinfo:
        _require_full_coverage(tasks, covered_task_ids=set(covered), rollouts_path=rollouts)
    message = str(excinfo.value)
    assert str(rollouts) in message  # points at the bundle
    assert "rollouts_failures.jsonl" in message  # ...and the sidecar
    assert str(tmp_path) in message  # ...and the work dir holding gym_env.log / gym_eval.*.log
    assert str(len(tasks) - 1) in message  # says how many tasks went unrepresented


def test_full_coverage_passes_silently(tmp_path: Path) -> None:
    tasks = discover_gym_tasks(EXAMPLE)
    _require_full_coverage(tasks, covered_task_ids={t.id for t in tasks}, rollouts_path=tmp_path / "rollouts.jsonl")


def test_reward_metric_shape() -> None:
    metric = GymRewardMetric()
    assert metric.type == "gym_reward"
    assert len(metric.output_spec()) == 1


@pytest.mark.asyncio
async def test_reward_metric_missing_reward_is_unscored_not_zero() -> None:
    metric = GymRewardMetric()
    scored = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(metadata={"reward": 1.0}))
    )
    assert scored.outputs[0].value == 1.0
    # A missing reward must be unscored (None -> nan, excluded from the mean), not a spurious 0.0.
    unscored = await metric.compute_scores(MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(metadata={})))
    assert unscored.outputs[0].value is None


def test_real_fixture_carries_the_schema_the_runner_reads() -> None:
    # Contract guard: the captured mcqa rollout bundle has the fields the runner depends on.
    records = _rows(ROLLOUTS)
    assert records
    for record in records:
        for key in ("responses_create_params", "response", "reward", "_ng_task_index", "_ng_rollout_index"):
            assert key in record, key


def test_aggregate_metrics_sidecar_with_invalid_utf8_is_skipped_not_raised(tmp_path: Path) -> None:
    # UnicodeDecodeError is a ValueError, not an OSError, so it slipped past the parse handler and would
    # raise straight out of run_tasks -- discarding every trial from a collection that already succeeded.
    rollouts_path = tmp_path / "rollouts.jsonl"
    _aggregate_metrics_path_for(rollouts_path).write_bytes(b'[{"agent_ref": {"name": "a"}, "x": \xff}]')

    assert _read_run_aggregations(rollouts_path) is None


# ---------------------------------------------------------------------------
# Config pre-flight: override serialization, selection args, `gym env validate`
# ---------------------------------------------------------------------------


def test_hydra_scalars_use_hydra_spellings_not_python_ones() -> None:
    # `str(None)` is "None" and `str(True)` is "True" — both of which Hydra reads back as *strings*,
    # silently setting the literal text instead of a null or a boolean.
    assert _hydra_scalar(None) == "null"
    assert _hydra_scalar(True) == "true"
    assert _hydra_scalar(False) == "false"
    assert _hydra_scalar([1, None]) == "[1,null]"
    assert _hydra_scalar(0.7) == "0.7"


def test_hydra_strings_are_quoted_so_the_grammar_cannot_retype_them() -> None:
    # Hydra's grammar is typed: unquoted, "true" parses as a bool, "null" as None, "1.5" as a float,
    # and "a,b" as a *sweep* — so a string override would silently become something else.
    assert _hydra_scalar("true") == "'true'"
    assert _hydra_scalar("null") == "'null'"
    assert _hydra_scalar("1.5") == "'1.5'"
    assert _hydra_scalar("a,b") == "'a,b'"
    assert _hydra_scalar("A[B") == "'A[B'"  # unquoted this does not parse at all
    assert _hydra_scalar("") == "''"
    # Only the quote is escaped: Hydra does not decode `\\` inside a quoted value, so escaping
    # backslashes would double them.
    assert _hydra_scalar("he'llo") == "'he\\'llo'"
    assert _hydra_scalar("back\\slash") == "'back\\slash'"
    # Interpolation survives quoting — the override sets the text, OmegaConf resolves it on read.
    assert _hydra_scalar("${policy_base_url}") == "'${policy_base_url}'"


def test_hydra_rejects_a_value_it_cannot_express() -> None:
    # A trailing backslash escapes the closing quote and leaves the value unterminated; there is no
    # spelling that avoids it, so say so rather than emit something unparseable.
    with pytest.raises(ValueError, match="ends with a backslash"):
        _hydra_scalar("ends\\")


def test_hydra_dicts_nested_in_a_list_use_the_grammars_bare_keys() -> None:
    # A mapping reached through a list has no dotted path to flatten onto, so it has to be spelled
    # inline. `str()` would emit Python's repr — `{'b': 1}` — whose quoted keys Hydra's `dictKey`
    # rule has no form for and rejects outright.
    assert _hydra_scalar({"b": 1}) == "{b:1}"
    assert _hydra_scalar([{"b": 1}, {"c": "true"}]) == "[{b:1},{c:'true'}]"
    # The typed spellings hold at depth: values recurse through the same function.
    assert _hydra_scalar({"b": None, "c": True, "d": "a,b"}) == "{b:null,c:true,d:'a,b'}"
    assert _hydra_scalar({"b": {"c": [1, "x"]}}) == "{b:{c:[1,'x']}}"
    assert _hydra_scalar({}) == "{}"


@pytest.mark.parametrize("key", ["true", "NULL", "1.5", "inf", "b:c", "b,c", "b}c", "b'c", "", 1])
def test_hydra_rejects_dict_keys_it_would_retype_or_fail_to_parse(key: object) -> None:
    # Keys are emitted bare because the grammar has no quoted form, which leaves them at the mercy
    # of the lexer: `{true:1}` keys on the boolean True and `{b:c:1}` does not parse. Neither is what
    # the caller wrote, and the second is not even loud, so refuse both.
    with pytest.raises(ValueError, match="dict key"):
        _hydra_scalar([{key: 1}])


def test_flatten_overrides_produces_forcing_dotted_paths() -> None:
    flattened = _flatten_overrides({"a": {"b": {"c": 1}}, "d": "x"})
    # `++` not `+`: a bare `+` fails on a key the merged config already defines, which is precisely
    # the case an override exists for.
    assert flattened == ["++a.b.c=1", "++d='x'"]
    assert _flatten_overrides({}) == []


def test_flatten_overrides_keeps_an_empty_mapping_instead_of_dropping_it() -> None:
    # An empty mapping has no leaves to descend to, so recursing emits nothing and the override
    # vanishes — the caller asked to clear `a` and the run would silently keep the config's value.
    assert _flatten_overrides({"a": {}}) == ["++a={}"]


def test_flatten_overrides_serializes_a_list_of_dicts() -> None:
    assert _flatten_overrides({"a": {"b": [{"c": 1}]}}) == ["++a.b=[{c:1}]"]


def _config(**kwargs: object) -> GymRuntimeConfig:
    return GymRuntimeConfig(agent="simple_agent", agent_config="cfg.yaml", resources_server="mcqa", **kwargs)  # type: ignore[arg-type]


def test_selection_binds_the_resources_server_by_default(tmp_path: Path) -> None:
    selection = _selection_args(_config(), tmp_path)
    assert "--resources-server" in selection and "mcqa" in selection
    assert "+simple_agent.responses_api_agents.simple_agent.resources_server.name=mcqa" in selection


def test_selection_omits_the_binding_when_the_caller_binds_it_themselves(tmp_path: Path) -> None:
    # gdpval registers its server as `gdpval_resources_server`, so the automatic binding is wrong for
    # it and the caller supplies their own. Emitting both would leave the config ambiguous.
    selection = _selection_args(
        _config(
            bind_resources_server=False,
            env_overrides={
                "simple_agent": {"responses_api_agents": {"simple_agent": {"resources_server": {"name": "other"}}}}
            },
        ),
        tmp_path,
    )
    assert not [arg for arg in selection if arg.startswith("+simple_agent.")]
    assert "++simple_agent.responses_api_agents.simple_agent.resources_server.name='other'" in selection


def test_selection_redirects_hydra_output_under_the_run_work_dir(tmp_path: Path) -> None:
    # Gym writes `outputs/<date>/<time>/` relative to cwd, and the subprocesses inherit ours so Gym
    # can find env.yaml — so without this every run litters the caller's directory.
    selection = _selection_args(_config(), tmp_path)
    assert f"hydra.run.dir={tmp_path / 'gym_hydra'}" in selection


def _stub_gym(tmp_path: Path, *, exit_code: int, message: str) -> str:
    """A stand-in for the `gym` CLI that records its argv and exits how the test wants."""
    script = tmp_path / "stub-gym"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(tmp_path / 'argv.txt')!r}).write_text('\\n'.join(sys.argv[1:]))\n"
        f"print({message!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


@pytest.mark.asyncio
async def test_validate_config_passes_the_selection_and_logs_the_report(tmp_path: Path) -> None:
    runner = GymAgentTaskRunner(config=_config())
    gym = _stub_gym(tmp_path, exit_code=0, message="Config is valid.")

    await runner._validate_config(gym, ["--resources-server", "mcqa"], {}, tmp_path)

    assert (tmp_path / "argv.txt").read_text().splitlines() == ["env", "validate", "--resources-server", "mcqa"]
    # Kept next to the run's other logs so a passing pre-flight is still auditable afterwards.
    assert (tmp_path / "gym_validate.log").read_text().strip() == "Config is valid."


@pytest.mark.asyncio
async def test_validate_config_raises_with_gyms_own_report(tmp_path: Path) -> None:
    # The whole point of the pre-flight: surface Gym's diagnosis before a Ray cluster and several
    # uvicorn servers start, rather than as a readiness timeout that says nothing about the cause.
    complaint = "Error: references resources_servers/'gdpval', which is not defined"
    runner = GymAgentTaskRunner(config=_config())
    gym = _stub_gym(tmp_path, exit_code=1, message=complaint)

    with pytest.raises(RuntimeError) as excinfo:
        await runner._validate_config(gym, [], {}, tmp_path)

    assert complaint in str(excinfo.value)
    assert "mcqa" in str(excinfo.value)


def test_gym_executable_reports_how_to_install_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="own environment"):
        _gym_executable()
