# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The handoff contract between Eval Author's split and Experimentalist's consumption of it.

Eval Author materializes the two Insight halves; the loop then reads provenance off each
one, hides the validation half, and blocks shell access to it. Those live on opposite sides
of a plugin boundary, so the pieces are pinned together here against a real materialized
suite rather than a hand-built ``Dataset``.
"""

from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author.materialization import (
    InsightSuite,
    InsightSuiteSplit,
    materialize_insight_split,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Task
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import (
    HELD_OUT_STORAGE_DIR,
    INSIGHT_TRAIN_SPLIT,
    INSIGHT_VALIDATION_SPLIT,
    ensure_heldout_hidden,
)
from nemo_experimentalist_plugin.experimentalist.components.insight_promotion import insight_suite_provenance
from nemo_experimentalist_plugin.experimentalist.components.tools import GuardedShellTools

_TASK_TOML = """
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

schema_version = "1.1"

[task]
name = "example/template__placeholder"

[metadata]
difficulty = "easy"

[environment]
build_timeout_sec = 60.0
""".lstrip()


def _write_template(root: Path) -> Task:
    root.mkdir(parents=True)
    (root / "task.toml").write_text(_TASK_TOML, encoding="utf-8")
    (root / "instruction.md").write_text("{{ instruction }}\n", encoding="utf-8")
    (root / "environment").mkdir()
    (root / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test.sh").write_text("#!/bin/sh\nmkdir -p /logs/verifier\necho 1 > /logs/verifier/reward.txt\n")
    return Task(id="task-template", uri=root.as_uri())


@pytest.fixture
def split(tmp_path: Path) -> InsightSuiteSplit:
    template = _write_template(tmp_path / "template")
    refs = [f"trace-{index}" for index in range(1, 5)]
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(refs)
    for task in staged:
        (task.path / "instruction.md").write_text(f"Reproduce {task.trace_ref}.\n", encoding="utf-8")
        suite.validate(task)
    suite.promote_local(refs, staged)
    return materialize_insight_split(
        suite.finalize(),
        train_dir=tmp_path / "dataset" / INSIGHT_TRAIN_SPLIT,
        validation_dir=tmp_path / "dataset" / INSIGHT_VALIDATION_SPLIT,
    )


def test_each_half_satisfies_the_provenance_the_loop_requires(split: InsightSuiteSplit) -> None:
    assert split.train is not None and split.validation is not None
    provenances = [insight_suite_provenance(half.dataset) for half in (split.train, split.validation)]

    train_provenance, validation_provenance = provenances
    assert train_provenance.identity != validation_provenance.identity
    for provenance, half in zip(provenances, (split.train, split.validation), strict=True):
        assert provenance.identity == half.identity
        assert provenance.scorer_identity == half.scorer_identity
        assert provenance.suite_path == half.path.resolve()
        assert set(provenance.task_hashes) == {task.id for task in half.dataset.list_tasks()}


def test_the_halves_partition_the_authored_suite(split: InsightSuiteSplit) -> None:
    assert split.train is not None and split.validation is not None
    train_tasks = {task.id for task in split.train.dataset.list_tasks()}
    validation_tasks = {task.id for task in split.validation.dataset.list_tasks()}

    assert not train_tasks & validation_tasks
    assert len(train_tasks) == len(validation_tasks) == 2


def test_the_validation_half_lands_where_the_holdout_mechanism_looks_for_it(
    split: InsightSuiteSplit,
    tmp_path: Path,
) -> None:
    assert split.validation is not None
    assert split.validation.path == tmp_path / "dataset" / INSIGHT_VALIDATION_SPLIT

    ensure_heldout_hidden(tmp_path)

    assert not split.validation.path.exists()
    hidden = tmp_path / HELD_OUT_STORAGE_DIR / INSIGHT_VALIDATION_SPLIT
    assert {path.name for path in hidden.iterdir()} >= {task.id for task in split.validation.dataset.list_tasks()}


async def test_the_shell_refuses_the_validation_half_by_its_materialized_path(
    split: InsightSuiteSplit,
    tmp_path: Path,
) -> None:
    assert split.validation is not None
    task_id = next(task.id for task in split.validation.dataset.list_tasks())
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run(f"cat dataset/{INSIGHT_VALIDATION_SPLIT}/{task_id}/instruction.md")
    finally:
        await shell.close()

    assert not result.success
    assert result.stdout == ""
