# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public types and aliases for the evaluator plugin SDK."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypeAlias

from nemo_evaluator_sdk.values import (
    DatasetInput,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from pydantic import Field, RootModel


class FilesetRef(RootModel):
    """Reference to a persisted Fileset in the Files API."""

    root: str = Field(
        description="Reference to a Fileset (format: workspace/fileset-name).",
        examples=["default/eval-dataset"],
    )

    def with_fragment(self, fragment: str) -> "FilesetRef":
        """Return a new fileset reference with a file path fragment appended."""
        normalized_fragment = fragment.lstrip("/")
        if not normalized_fragment:
            raise ValueError("FilesetRef fragment cannot be empty.")
        if "#" in normalized_fragment:
            raise ValueError("FilesetRef fragment cannot contain '#'.")
        if "#" in self.root:
            raise ValueError("FilesetRef already includes a fragment.")
        return FilesetRef(root=f"{self.root}#{normalized_fragment}")


# TODO: remove this type if we decide nemo_evaluator_sdk will not support remote execution.
ExecutionMode: TypeAlias = Literal["local", "remote"]
PluginDatasetInput: TypeAlias = DatasetInput | str | Path | FilesetRef

__all__ = [
    "RunConfig",
    "RunConfigOnline",
    "RunConfigOnlineModel",
    "ExecutionMode",
    "PluginDatasetInput",
]
