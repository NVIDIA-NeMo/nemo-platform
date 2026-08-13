# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the compact smoke-task manifest into Harbor task directories."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskSpec:
    """The authored values for one curated task."""

    group: str
    split: str
    id: str
    question: str
    expected: str
    format: str
    legacy_environment_comment: bool

    @property
    def name(self) -> str:
        """Return the Harbor task name."""
        return f"smoke/{self.group.split('-', 1)[0]}-{self.id}"


def load_tasks(dataset_dir: Path) -> list[TaskSpec]:
    """Load the compact curated-task manifest."""
    payload = json.loads((dataset_dir / "tasks.json").read_text(encoding="utf-8"))
    entries = payload.get("tasks")
    if not isinstance(entries, list):
        raise ValueError("tasks.json must contain a tasks list")
    tasks: list[TaskSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each task must be an object")
        try:
            task = TaskSpec(
                group=str(entry["group"]),
                split=str(entry["split"]),
                id=str(entry["id"]),
                question=str(entry["question"]),
                expected=str(entry["expected"]),
                format=str(entry["format"]),
                legacy_environment_comment=bool(entry["legacy_environment_comment"]),
            )
        except KeyError as exc:
            raise ValueError(f"task is missing {exc.args[0]!r}") from exc
        if not task.group or not task.split or not task.id or not task.question or not task.expected:
            raise ValueError(f"task {task!r} has an empty required value")
        if "=" not in task.expected:
            raise ValueError(f"task {task.id!r} expected value has no key")
        tasks.append(task)
    if len({(task.group, task.split, task.id) for task in tasks}) != len(tasks):
        raise ValueError("tasks.json contains duplicate group/split/id entries")
    return tasks


def render(dataset_dir: Path) -> list[Path]:
    """Render every curated task from ``task-template`` and return their paths."""
    template = dataset_dir / "task-template"
    groups = dataset_dir / "groups"
    if not template.is_dir():
        raise FileNotFoundError(f"task template not found: {template}")
    groups.mkdir(exist_ok=True)
    for path in groups.iterdir():
        if path.name == ".gitignore":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    written: list[Path] = []
    for task in load_tasks(dataset_dir):
        destination = groups / task.group / task.split / task.id
        shutil.copytree(template, destination, ignore=shutil.ignore_patterns("README.md", "records.json"))
        _render_task(destination, task)
        written.append(destination)
    return written


def _render_task(destination: Path, task: TaskSpec) -> None:
    """Fill one copied task template."""
    replacements = {
        "<QUESTION>": task.question,
        "<FIELD>": task.format.partition("=")[0],
        "<EXPECTED>": task.expected,
        'name = "smoke/generated"': f'name = "{task.name}"',
        'keywords = ["smoke", "g1"]': f'keywords = ["smoke", "{task.group.split("-", 1)[0]}"]',
    }
    for relative in ("instruction.md", "task.toml", "tests/expected.txt"):
        path = destination / relative
        text = path.read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        if relative == "instruction.md":
            text = text.replace(f"{task.format.partition('=')[0]}=<result>", task.format)
        if relative == "task.toml" and task.legacy_environment_comment:
            text = text.replace(
                "Tasks ship no environment/ directory.",
                "environment/ stays empty: Harbor\n# requires the directory, and a Dockerfile would shadow the prebuilt image.",
            )
        remaining = [placeholder for placeholder in ("<QUESTION>", "<FIELD>", "<EXPECTED>") if placeholder in text]
        if remaining:
            raise ValueError(f"unfilled placeholder in {path}: {remaining}")
        path.write_text(text, encoding="utf-8")


def main() -> None:
    """Render curated tasks from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dataset",
    )
    args = parser.parse_args()
    for path in render(args.dataset_dir):
        print(path.relative_to(args.dataset_dir))


if __name__ == "__main__":
    main()
