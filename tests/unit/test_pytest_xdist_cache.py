# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from tests.xdist_cache import xdist_worker_xdg_cache_home


def test_xdist_worker_xdg_cache_home_uses_worker_specific_path(tmp_path):
    environ = {
        "XDG_CACHE_HOME": str(tmp_path),
        "PYTEST_XDIST_TESTRUNUID": "run123",
        "PYTEST_XDIST_WORKER": "gw2",
    }

    assert xdist_worker_xdg_cache_home(environ) == str(tmp_path / "pytest-xdist" / "run123" / "gw2")


def test_xdist_worker_xdg_cache_home_skips_non_xdist_process():
    assert xdist_worker_xdg_cache_home({}) is None
