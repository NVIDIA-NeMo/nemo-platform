# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The dataset profiler core.

A dependency-free library (pyarrow + stdlib) that reads dataset files through a
:class:`~nemo_datasets_plugin.profiler.file_source.FileSource` seam and per-format readers, and — in
later commits — measures and classifies them into a ``DatasetProfile``.
"""

from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource, LocalFileSource

__all__ = ["FileEntry", "FileSource", "LocalFileSource"]
