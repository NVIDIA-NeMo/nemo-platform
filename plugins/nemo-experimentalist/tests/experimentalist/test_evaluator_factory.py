# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Sequence

import pytest
from nemo_experimentalist_plugin.entities import DatasetRef, Task
from nemo_experimentalist_plugin.experimentalist import roles
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Dataset,
    EvaluatorConfig,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import DatasetFactory, EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_native import (
    HarborEvaluatorConfig,
    HarborNativeOutcomeEvaluator,
)

_UNSUPPORTED_TYPE = "unsupported"
_SUPPORTED_TYPE = "concrete"
_NONEXISTENT_URI = "/tmp/nonexistent.jsonl"


class ConcreteDataset(Dataset):
    """Takes a jsonl file with every line being a task."""

    @classmethod
    def from_ref(cls, ref: DatasetRef) -> "ConcreteDataset":
        tasks = cls._from_jsonl(ref.uri)
        return cls(id=ref.uri, source=ref, tasks=tasks)

    @staticmethod
    def _from_jsonl(uri: str) -> list[Task]:
        with open(uri, "r") as f:
            return [
                Task(
                    id=f"task_{line_number}",
                    uri=f"{uri}#L{line_number}",
                    description=f"task {line_number}",
                    inputs=json.loads(line),
                )
                for line_number, line in enumerate(f, start=1)
                if line.strip()
            ]


class ConcreteEvaluator(roles.OutcomeEvaluator):
    """A registered evaluation component, the way a separate package would ship one."""

    name = _SUPPORTED_TYPE
    dataset_type = ConcreteDataset
    config_type = EvaluatorConfig

    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        return []


def test_build_dataset_raises_on_a_name_no_component_claims() -> None:
    """Never falls back to the built-in: a run configured for one evaluator must not
    silently be measured by another."""
    with pytest.raises(LookupError, match="no outcome-evaluator registered"):
        DatasetFactory().build_dataset(_UNSUPPORTED_TYPE, DatasetRef(uri=_NONEXISTENT_URI, description="test"))


def test_build_dataset_uses_the_dataset_the_component_declares(tmp_path):
    """The component owns its Dataset type, so naming it in config is enough.

    A table of the types this package knows is what stopped `evaluation:` being
    swappable — it resolved by name and then died on a hardcoded lookup.
    """
    jsonl = tmp_path / "tasks.jsonl"
    rows = [
        {"question": "What is 2+2?", "answer": "4"},
        {"question": "Capital of France?", "answer": "Paris"},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    dataset = DatasetFactory().build_dataset(_SUPPORTED_TYPE, DatasetRef(uri=str(jsonl), description="test"))
    assert len(dataset.list_tasks()) == 2
    assert isinstance(dataset, ConcreteDataset)


def test_concrete_dataset_raises_on_nonexistent_file():
    ref = DatasetRef(uri=_NONEXISTENT_URI, description="test")
    with pytest.raises(FileNotFoundError):
        ConcreteDataset.from_ref(ref)


def test_concrete_dataset_empty_file(tmp_path):
    jsonl = tmp_path / "empty.jsonl"
    jsonl.write_text("")
    dataset = ConcreteDataset.from_ref(DatasetRef(uri=str(jsonl), description="empty"))
    assert dataset.list_tasks() == []


def test_concrete_dataset_loads_tasks(tmp_path):
    jsonl = tmp_path / "tasks.jsonl"
    rows = [
        {"question": "What is 2+2?", "answer": "4"},
        {"question": "Capital of France?", "answer": "Paris"},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    dataset = ConcreteDataset.from_ref(DatasetRef(uri=str(jsonl), description="test"))
    tasks = dataset.list_tasks()

    assert len(tasks) == 2
    assert tasks[0].id == "task_1"
    assert tasks[0].uri == f"{jsonl}#L1"
    assert tasks[0].inputs == rows[0]
    assert tasks[1].id == "task_2"
    assert tasks[1].inputs == rows[1]


def test_build_dataset_falsy_evaluator_type():
    with pytest.raises(ValueError, match="Evaluator type and dataset reference are required"):
        DatasetFactory().build_dataset("", DatasetRef(uri="/tmp/x"))


def test_build_dataset_falsy_dataset_ref():
    with pytest.raises(ValueError, match="Evaluator type and dataset reference are required"):
        DatasetFactory().build_dataset("harbor-native", None)


def test_build_task_template_zero_tasks(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "not-a-task").mkdir()
    with pytest.raises(ValueError, match="contains no Harbor task directories"):
        DatasetFactory().build_task_template("harbor-native", DatasetRef(uri=str(empty_dir)))


def test_build_task_template_multiple_tasks(tmp_path):
    dataset_dir = tmp_path / "ds"
    (dataset_dir / "task-a").mkdir(parents=True)
    (dataset_dir / "task-a" / "task.toml").write_text("")
    (dataset_dir / "task-b").mkdir()
    (dataset_dir / "task-b" / "task.toml").write_text("")
    with pytest.raises(ValueError, match="exactly one harbor-native task"):
        DatasetFactory().build_task_template("harbor-native", DatasetRef(uri=str(dataset_dir)))


def test_build_task_template_single_task(tmp_path):
    task_dir = tmp_path / "task-only"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("")
    task = DatasetFactory().build_task_template("harbor-native", DatasetRef(uri=str(task_dir)))
    assert task.id == "task-only"


def test_evaluator_factory_build_evaluator_with_config():
    factory = EvaluatorFactory()
    evaluator = factory.build_evaluator("harbor-native", HarborEvaluatorConfig())
    assert isinstance(evaluator, HarborNativeOutcomeEvaluator)


def test_evaluator_factory_build_evaluator_with_dict():
    factory = EvaluatorFactory()
    evaluator = factory.build_evaluator("harbor-native", {"import_path": "x:Y"})
    assert isinstance(evaluator, HarborNativeOutcomeEvaluator)


def test_harbor_orchestrators_live_outside_the_shared_harbor_module():
    factory = EvaluatorFactory()

    native = factory.build_evaluator("harbor-native", {})
    sdk_backed = factory.build_evaluator("harbor-runner", {})

    assert type(native).__module__ == ("nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_native")
    assert type(sdk_backed).__module__ == (
        "nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_evaluator"
    )


def test_evaluator_factory_build_evaluator_unsupported():
    factory = EvaluatorFactory()
    with pytest.raises(LookupError, match="no outcome-evaluator registered"):
        factory.build_evaluator("unsupported", {})


def test_evaluator_factory_build_evaluator_wrong_config_type():
    factory = EvaluatorFactory()
    with pytest.raises(TypeError, match="'harbor-native' evaluator config must be an EvaluatorConfig or dict"):
        factory.build_evaluator("harbor-native", 42)
