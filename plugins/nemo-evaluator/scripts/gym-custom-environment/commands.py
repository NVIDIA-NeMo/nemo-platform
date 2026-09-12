# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Internal subprocess wrapper shared by prerequisite and workflow modules.

The wrapper executes argument vectors without a shell, merges only explicit
environment overrides, converts command failures into readable exceptions, and
optionally records stdout as evidence. Developers do not invoke this module.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO


class CommandError(RuntimeError):
    """Raised when an external command exits unsuccessfully."""


class CommandRunner:
    """Run argument-vector commands without shell interpolation."""

    def __init__(self, *, working_directory: Path) -> None:
        """Configure the working directory shared by child processes."""
        self.working_directory = working_directory

    def run(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        input_text: str | None = None,
        output_path: Path | None = None,
    ) -> str:
        """Run a command, optionally supply stdin, and return captured stdout."""
        command_environment = os.environ.copy()
        if environment:
            command_environment.update(environment)
        try:
            result = subprocess.run(
                list(arguments),
                cwd=self.working_directory,
                env=command_environment,
                input=input_text,
                text=True,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or error.stdout.strip() or f"exit code {error.returncode}"
            command = " ".join(arguments)
            raise CommandError(f"{command} failed: {detail}") from error

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.stdout, encoding="utf-8")
        return result.stdout

    def run_json(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        input_text: str | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Run a command and require its stdout to contain a JSON object."""
        output = self.run(
            arguments,
            environment=environment,
            input_text=input_text,
            output_path=output_path,
        )
        value = json.loads(output)
        if not isinstance(value, dict):
            command = " ".join(arguments)
            raise CommandError(f"{command} did not return a JSON object")
        return value

    def start(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        stdout: TextIO | int | None = None,
    ) -> subprocess.Popen[str]:
        """Start a long-running command and return its process handle."""
        command_environment = os.environ.copy()
        if environment:
            command_environment.update(environment)
        return subprocess.Popen(
            list(arguments),
            cwd=self.working_directory,
            env=command_environment,
            text=True,
            stdout=stdout,
            stderr=subprocess.STDOUT,
        )
