# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Top-level conftest: runs before any test module is imported.

Eval Author and Experimentalist agents call get_smart_model() at class-definition
time. Placeholder credentials keep collection working when real keys are absent.
setdefault does not overwrite CI or developer-provided values.
"""

import os

import litellm
import pytest

os.environ.setdefault("AUTHOR_API_BASE", "http://placeholder-for-import")
os.environ.setdefault("AUTHOR_API_KEY", "placeholder-for-import")
os.environ.setdefault("EXPERIMENTALIST_API_BASE", "http://placeholder-for-import")
os.environ.setdefault("EXPERIMENTALIST_API_KEY", "placeholder-for-import")

litellm.drop_params = True


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes that monkeypatch cannot restore."""
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
