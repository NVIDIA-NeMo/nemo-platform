# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Factories for evaluator-specific datasets and evaluators."""

from pathlib import Path
from typing import Any, Protocol, cast

from nemo_experimentalist_plugin.entities import Dataset, DatasetRef, Task
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorConfig, EvaluatorType
from nemo_experimentalist_plugin.experimentalist.registry import resolve
from nemo_experimentalist_plugin.experimentalist.roles import OutcomeEvaluator


class EvaluatorDataset(Protocol):
    """Dataset construction contract supplied by an outcome evaluator."""

    @classmethod
    def from_ref(cls, ref: DatasetRef, **options: Any) -> Dataset:
        """Build an evaluator-specific dataset from a source reference."""


def _evaluation(name: EvaluatorType) -> type[OutcomeEvaluator]:
    """The registered `outcome-evaluator` component called *name*.

    Resolved rather than looked up in a table: a table keyed on the names this package
    knows is exactly what stops `outcome_evaluator:` being swappable from config. The
    two Harbor-backed evaluators are entries in the registry like any other.
    """
    return cast(type[OutcomeEvaluator], resolve("outcome-evaluator", name))


class DatasetFactory:
    """Build evaluator-compatible Dataset objects from source references."""

    def build_dataset(
        self,
        evaluator_type: EvaluatorType,
        dataset_ref: DatasetRef,
        **options: Any,
    ) -> Dataset:
        """Build a Dataset for the selected evaluator type.

        Args:
            evaluator_type(EvaluatorType): The type of evaluator to build the dataset for.
            dataset_ref(DatasetRef): The reference to the dataset to build.
            **options: Forwarded to the dataset type's ``from_ref``. ``allow_empty=True``
                is what lets an Insight-driven run start with splits the Eval Author has
                not filled yet.

        Returns:
            Dataset: The built dataset.

        Raises:
            ValueError: If the evaluator type or dataset reference is not provided or if the evaluator type is not supported.
        """
        if not evaluator_type or not dataset_ref:
            raise ValueError("Evaluator type and dataset reference are required")
        component = _evaluation(evaluator_type)
        dataset_type = cast(type[EvaluatorDataset], component.dataset_type)
        return dataset_type.from_ref(dataset_ref, **options)

    def build_task_template(
        self,
        evaluator_type: EvaluatorType,
        template_ref: DatasetRef,
    ) -> Task:
        """Parse an evaluator-specific template directory as one task.

        Args:
            evaluator_type(EvaluatorType): The type of evaluator to build the task template for.
            template_ref(DatasetRef): The reference to the template directory to build.
                A template directory is a directory that contains a single task template containing placeholder values for the task.

        Returns:
            Task: The built task.
        """
        tasks = list(
            self.build_dataset(
                evaluator_type,
                template_ref,
                single_task=True,
            ).list_tasks()
        )
        if len(tasks) != 1:
            raise ValueError(f"Task template must contain exactly one {evaluator_type} task; found {len(tasks)}")
        return tasks[0]


class EvaluatorFactory:
    """Build concrete evaluators from evaluator type."""

    def build_evaluator(
        self,
        evaluator_type: EvaluatorType,
        config: EvaluatorConfig | dict[str, Any],
        *,
        experiment_dir: Path | None = None,
    ) -> OutcomeEvaluator:
        """Build an Evaluator for the selected evaluator type.

        Args:
            evaluator_type(EvaluatorType): The type of evaluator to build.
            config(EvaluatorConfig | dict[str, Any]): The configuration for the evaluator.
            experiment_dir(Path | None): The directory to store the experiment results.

        Returns:
            Evaluator: The built evaluator.

        Raises:
            ValueError: If the evaluator type is not supported.
            TypeError: If the evaluator config is not an EvaluatorConfig or dict.
        """
        component = _evaluation(evaluator_type)
        if isinstance(config, EvaluatorConfig):
            config = config.model_dump()
        elif not isinstance(config, dict):
            # Quoted rather than .capitalize()d: these names are hyphenated, so
            # capitalizing produced "Harbor-native" — and it silently changes shape
            # every time a component is renamed.
            raise TypeError(f"{evaluator_type!r} evaluator config must be an EvaluatorConfig or dict")
        return component(options=component.config_type.model_validate(config), experiment_dir=experiment_dir)
