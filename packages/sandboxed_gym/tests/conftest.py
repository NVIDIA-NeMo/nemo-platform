# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from sandboxed_gym.runtime import gym_host_runtime as runtime


@pytest.fixture
def isolated_gym_host_process_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests that execute the real ``_install_wheels_v1_dependencies`` helper.

    Use this fixture whenever a test reaches that helper directly or through
    ``bootstrap_gym_host``; tests that replace the helper with a mock do not need it.
    """
    # Restore the caller's uv wheel search path after the helper points it at the test wheelhouse.
    monkeypatch.delenv(runtime.UV_FIND_LINKS_ENV_KEY, raising=False)
    # Restore the caller's Python import path after the helper prepends its temporary install target.
    monkeypatch.delenv("PYTHONPATH", raising=False)
    # Let the helper mutate an isolated list, then restore the interpreter's original sys.path object.
    monkeypatch.setattr(runtime.sys, "path", runtime.sys.path.copy())
