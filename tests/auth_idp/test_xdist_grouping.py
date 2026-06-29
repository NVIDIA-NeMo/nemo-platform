# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.auth_idp.xdist import append_xdist_group_suffix

pytestmark = [pytest.mark.auth_idp]


def test_append_xdist_group_suffix_only_appends_once_and_sorts_groups():
    nodeid = "tests/auth_idp/test_authentik_real_oidc.py::test_authentik_machine_token_is_real"
    assert append_xdist_group_suffix(nodeid, {"idp-live"}) == f"{nodeid}@idp-live"
    assert append_xdist_group_suffix(nodeid, {"b", "a"}) == f"{nodeid}@a_b"
    assert append_xdist_group_suffix(f"{nodeid}@idp-live", {"idp-live"}) == f"{nodeid}@idp-live"
