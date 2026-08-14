# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The dataset directory shape Harbor evaluates: a directory of task directories.

Harbor's ``DatasetConfig`` enumerates the *children* of a dataset path and keeps
the ones that are task directories. It never reads the dataset path itself as a
task, so a dataset whose tasks Harbor cannot enumerate is rejected by its job
config rather than by anything we validate first.

Preflight reads this contract as well and cannot import ``harbor`` — whether
harbor is importable is one of its own checks — so the rule lives here, in a
module that imports only the standard library.
"""

from pathlib import Path

TASK_CONFIG_FILENAME = "task.toml"
_TASK_TEMPLATE_DIRNAME = "task_template"


def is_task_dir(path: Path) -> bool:
    """Return whether *path* is a Harbor task directory."""
    return path.is_dir() and (path / TASK_CONFIG_FILENAME).exists()


def find_task_dirs(dataset_path: Path) -> list[Path]:
    """Return the task directories *dataset_path* holds, in a stable order.

    A ``task_template`` child is the shape generated tasks are cut from, not a
    task of the dataset, so it is left out.
    """
    return sorted(
        child for child in dataset_path.iterdir() if child.name != _TASK_TEMPLATE_DIRNAME and is_task_dir(child)
    )
