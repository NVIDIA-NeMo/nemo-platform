# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo-NB: Jupyter Notebook Preprocessor for Sphinx.

This extension converts Jupyter notebooks (.ipynb) to Markdown (.md) at the
builder-inited stage, enabling full Sphinx directive support including
tab-sets, dropdowns, and nested structures.

Features:
- Marker-based commands (# @nemo-nb: COMMAND)
- Context-aware indentation
- Tab-sets, dropdowns, and directive wrapping
- Multi-cell grouping and conditional content
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

try:
    __version__ = _package_version("nemo-nb")
except PackageNotFoundError:
    __version__ = "0.0.0"

# Import converter for CLI usage
from .converter import NotebookConverter

# Import discovery utilities
from .discovery import (
    EXCLUDED_DIRS,
    EXCLUDED_FILENAMES,
    NotebookDiscoveryResult,
    expand_literalincludes,
    find_processable_notebooks,
    find_testable_notebooks,
    has_process_marker_markdown,
    has_process_marker_notebook,
    has_skip_test_marker_markdown,
    has_skip_test_marker_notebook,
    is_excluded_file,
    is_in_excluded_dir,
    print_conflicts_error,
)

# Import markdown to notebook converter
from .md_to_notebook import MarkdownToNotebookConverter, expand_includes

# Import setup only when sphinx is available
try:
    from .sphinx import setup

    __all__ = [
        "setup",
        "NotebookConverter",
        "MarkdownToNotebookConverter",
        "expand_includes",
        "expand_literalincludes",
        "find_processable_notebooks",
        "find_testable_notebooks",
        "has_process_marker_markdown",
        "has_process_marker_notebook",
        "has_skip_test_marker_markdown",
        "has_skip_test_marker_notebook",
        "is_excluded_file",
        "is_in_excluded_dir",
        "print_conflicts_error",
        "NotebookDiscoveryResult",
        "EXCLUDED_DIRS",
        "EXCLUDED_FILENAMES",
    ]
except ImportError:
    # Sphinx not available - probably running tests
    __all__ = [
        "NotebookConverter",
        "MarkdownToNotebookConverter",
        "expand_includes",
        "expand_literalincludes",
        "find_processable_notebooks",
        "find_testable_notebooks",
        "has_process_marker_markdown",
        "has_process_marker_notebook",
        "has_skip_test_marker_markdown",
        "has_skip_test_marker_notebook",
        "is_excluded_file",
        "is_in_excluded_dir",
        "print_conflicts_error",
        "NotebookDiscoveryResult",
        "EXCLUDED_DIRS",
        "EXCLUDED_FILENAMES",
    ]
