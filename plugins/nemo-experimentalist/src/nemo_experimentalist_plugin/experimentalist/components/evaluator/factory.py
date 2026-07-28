# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Factories for evaluator-specific datasets and evaluators."""

from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import Dataset, DatasetRef, Task

_SUPPORTED_EVALUATOR_TYPES = {
    "harbor": (HarborDataset, HarborEvaluator, HarborEvaluatorConfig),
}


class DatasetFactory:
    """Build evaluator-compatible Dataset objects from source references."""

    def __init__(
        self,
        supported_evaluator_types: dict[EvaluatorType, tuple[type[Dataset], type[Evaluator], type[EvaluatorConfig]]]
        | None = None,
    ) -> None:
        self.supported_evaluator_types = supported_evaluator_types or _SUPPORTED_EVALUATOR_TYPES

    def build_dataset(self, evaluator_type: EvaluatorType, dataset_ref: DatasetRef) -> Dataset:
        """Build a Dataset for the selected evaluator type.

        Args:
            evaluator_type(EvaluatorType): The type of evaluator to build the dataset for.
            dataset_ref(DatasetRef): The reference to the dataset to build.

        Returns:
            Dataset: The built dataset.

        Raises:
            ValueError: If the evaluator type or dataset reference is not provided or if the evaluator type is not supported.
        """
        if not evaluator_type or not dataset_ref:
            raise ValueError("Evaluator type and dataset reference are required")

        if evaluator_type not in self.supported_evaluator_types:
            raise ValueError(f"Unsupported evaluator type: {evaluator_type}")
        return self.supported_evaluator_types[evaluator_type][0].from_ref(dataset_ref)

    def build_task_template(self, evaluator_type: EvaluatorType, template_ref: DatasetRef) -> Task:
        """Parse an evaluator-specific template directory as one task.

        Args:
            evaluator_type(EvaluatorType): The type of evaluator to build the task template for.
            template_ref(DatasetRef): The reference to the template directory to build.
                A template directory is a directory that contains a single task template containing placeholder values for the task.

        Returns:
            Task: The built task.
        """
        tasks = list(self.build_dataset(evaluator_type, template_ref).list_tasks())
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
    ) -> Evaluator:
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
        if evaluator_type in _SUPPORTED_EVALUATOR_TYPES:
            if isinstance(config, EvaluatorConfig):
                config = config.model_dump()
            elif not isinstance(config, dict):
                raise TypeError(f"{evaluator_type.capitalize()} evaluator config must be an EvaluatorConfig or dict")
            evaluator_config = _SUPPORTED_EVALUATOR_TYPES[evaluator_type][2].model_validate(config)
            return _SUPPORTED_EVALUATOR_TYPES[evaluator_type][1](
                options=evaluator_config, experiment_dir=experiment_dir
            )

        raise ValueError(f"Unsupported evaluator type: {evaluator_type}")
