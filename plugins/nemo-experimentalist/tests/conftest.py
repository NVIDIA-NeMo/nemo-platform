# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Top-level conftest: runs before any test module is imported.

Coder and Proposer call get_smart_model() at class-definition time (class keyword
argument). That call needs an endpoint and a credential, so we satisfy it before pytest
imports any test module, here at module level using setdefault — real CI values are not
overwritten.
"""

import os

import litellm
import pytest
from nemo_platform_plugin.config import Configuration

os.environ.setdefault("NEMO_EXPERIMENTALIST_API_BASE", "http://placeholder-for-import")
os.environ.setdefault("NEMO_EXPERIMENTALIST_API_KEY", "placeholder-for-import")
# Tiers too, so constructing an agent does not depend on a developer's .env being loaded
# by the nooa import. Tests that care about tier resolution set their own values.
for _tier in ("SMART", "MID", "FAST"):
    os.environ.setdefault(f"NEMO_EXPERIMENTALIST_MODELS_{_tier}", "placeholder/for-import")

# Some NVIDIA inference endpoint models reject the tool_choice parameter.
# Drop unsupported params silently so the CodeAct strategy can call tools.
litellm.drop_params = True


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes that monkeypatch cannot, and unshare the settings cache.

    The CLI loads a profile's .env straight into os.environ. When the variable was
    previously unset, monkeypatch has nothing recorded to restore, so the value
    survives the test and leaks into whatever else the xdist worker runs next.

    ``ExperimentalistConfig.get()`` memoizes, so a test that sets endpoint or model
    variables would otherwise be read back by the next test — or, worse, would silently
    read the previous test's values itself. Overrides installed with
    ``Configuration.set_override`` outlive the test that set them for the same reason.
    Clearing both on either side of the yield keeps each test resolving its own settings.
    """
    snapshot = os.environ.copy()
    Configuration.clear_cache()
    Configuration.clear_overrides()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
    Configuration.clear_cache()
    Configuration.clear_overrides()
