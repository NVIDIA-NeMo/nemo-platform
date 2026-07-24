# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Top-level conftest: runs before any test module is imported.

Coder and Proposer call get_smart_model() at class-definition time (class keyword
argument). That call requires EXPERIMENTALIST_API_BASE and EXPERIMENTALIST_API_KEY to be set.
We must satisfy that requirement before pytest imports any test module, so we do it
here at module level using setdefault — real CI values are not overwritten.
"""

import os

import litellm
import pytest

os.environ.setdefault("EXPERIMENTALIST_API_BASE", "http://placeholder-for-import")
os.environ.setdefault("EXPERIMENTALIST_API_KEY", "placeholder-for-import")

# Some NVIDIA inference endpoint models reject the tool_choice parameter.
# Drop unsupported params silently so the CodeAct strategy can call tools.
litellm.drop_params = True


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes that monkeypatch cannot.

    The CLI loads a profile's .env straight into os.environ. When the variable was
    previously unset, monkeypatch has nothing recorded to restore, so the value
    survives the test and leaks into whatever else the xdist worker runs next.
    """
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
