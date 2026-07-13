# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Format readers, registered by importing this package.

Importing the package populates the registry (each reader module self-registers), so
:func:`get_reader` resolves every supported format.
"""

from nemo_datasets_plugin.profiler.readers.base import (
    FormatReader,
    ReadResult,
    detect_format,
    get_reader,
    register_reader,
)

# Import for side effects: each module calls register_reader() at import time.
from nemo_datasets_plugin.profiler.readers import jsonl as _jsonl  # noqa: F401  isort:skip
from nemo_datasets_plugin.profiler.readers import parquet as _parquet  # noqa: F401  isort:skip

__all__ = [
    "FormatReader",
    "ReadResult",
    "detect_format",
    "get_reader",
    "register_reader",
]
