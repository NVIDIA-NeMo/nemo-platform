# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fileset value objects for the evaluator plugin SDK."""

from __future__ import annotations

from pydantic import Field, RootModel


class FilesetRef(RootModel[str]):
    """Reference to a Fileset in the platform Files API.

    A reference is a string with format 'workspace/fileset-name' that points to a
    persisted fileset entity. When used as a dataset source, all files within the
    fileset will be downloaded to the job container.
    """

    root: str = Field(description="Reference to a Fileset (format: workspace/fileset-name).")

    def with_fragment(self, fragment: str) -> FilesetRef:
        """Return a new fileset reference with a file path fragment appended."""
        normalized_fragment = fragment.lstrip("/")
        if not normalized_fragment:
            raise ValueError("FilesetRef fragment cannot be empty.")
        if "#" in normalized_fragment:
            raise ValueError("FilesetRef fragment cannot contain '#'.")
        if "#" in self.root:
            raise ValueError("FilesetRef already includes a fragment.")
        return FilesetRef(root=f"{self.root}#{normalized_fragment}")


__all__ = ["FilesetRef"]
