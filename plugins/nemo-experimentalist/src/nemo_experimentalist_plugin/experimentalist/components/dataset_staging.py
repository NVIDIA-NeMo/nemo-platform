# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment-local staging and hydration for Eval Author inputs."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from nemo_experimentalist_plugin.entities import Dataset, DatasetRef, local_path_from_uri
from nemo_platform import AsyncNeMoPlatform


@dataclass(frozen=True, slots=True)
class _StagedEvalAuthorInputs:
    """Staged Eval Author references returned by this module's factory."""

    train_dataset: DatasetRef
    validation_dataset: DatasetRef
    task_template: DatasetRef


def distribute_insight_suite_tasks(
    insight_suite: Dataset,
    train_dataset: Dataset,
    validation_dataset: Dataset,
) -> None:
    """Assign Insight-suite tasks to validation/train at a deterministic 30/70 split.

    Eval Author retains the materialized suite as its provenance artifact. The
    optimizer consumes its tasks through the train and validation datasets,
    reserving the first 30 percent for validation and using the remaining 70
    percent for training feedback.
    """
    tasks = list(insight_suite.list_tasks())
    validation_count = (3 * len(tasks) + 9) // 10
    validation_dataset.add_tasks(tasks[:validation_count])
    train_dataset.add_tasks(tasks[validation_count:])


def _local_directory(ref: DatasetRef) -> Path:
    path = local_path_from_uri(ref.uri, context="Eval Author input").resolve()
    if not path.is_dir():
        raise ValueError(f"Eval Author input is not a directory: {path}")
    return path


def _stage(ref: DatasetRef, destination: Path) -> DatasetRef:
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_local_directory(ref), destination)
    return ref.model_copy(update={"uri": str(destination)})


async def stage_task_template(
    experiment_dir: Path,
    task_template: DatasetRef,
    *,
    client: AsyncNeMoPlatform,
    workspace: str,
) -> DatasetRef:
    """Refresh a local or Fileset-backed task template in experiment-local staging."""
    destination = experiment_dir.resolve() / "dataset" / "task-template"
    source = None
    if urlparse(task_template.uri).scheme != "fileset":
        source = _local_directory(task_template)
        if source == destination:
            return task_template.model_copy(update={"uri": str(destination)})

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(f"Eval Author task template staging path is not a directory: {destination}")
        shutil.rmtree(destination)

    if urlparse(task_template.uri).scheme == "fileset":
        try:
            await client.files.download(
                remote_path=task_template.uri,
                local_path=str(destination),
                workspace=workspace,
            )
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            raise
        if not destination.is_dir() or not any(path.is_file() for path in destination.rglob("*")):
            if destination.exists():
                shutil.rmtree(destination)
            raise ValueError(f"Eval Author Fileset task template contains no files: {task_template.uri}")
    else:
        assert source is not None
        shutil.copytree(source, destination)

    return task_template.model_copy(update={"uri": str(destination)})


async def stage_eval_author_inputs(
    experiment_dir: Path,
    *,
    train_dataset: DatasetRef,
    validation_dataset: DatasetRef,
    task_template: DatasetRef,
    client: AsyncNeMoPlatform,
    workspace: str,
) -> _StagedEvalAuthorInputs:
    """Stage mutable Eval Author inputs beneath the experiment directory."""
    dataset_dir = experiment_dir.resolve() / "dataset"
    return _StagedEvalAuthorInputs(
        train_dataset=_stage(train_dataset, dataset_dir / "train"),
        validation_dataset=_stage(validation_dataset, dataset_dir / "validation"),
        task_template=await stage_task_template(
            experiment_dir,
            task_template,
            client=client,
            workspace=workspace,
        ),
    )
