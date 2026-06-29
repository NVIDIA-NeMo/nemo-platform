# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from e2e.services_pool import RunningServices, _normalize_config, _start_config_sidecars

pytestmark = [pytest.mark.auth_idp]


def test_normalized_e2e_config_rejects_non_mapping_sidecars():
    with pytest.raises(pytest.UsageError, match="e2e_sidecars must be a mapping"):
        _normalize_config(
            {
                "e2e_sidecars": ["authentik"],
            }
        )


def test_start_config_sidecars_rejects_non_mapping_sidecars(tmp_path):
    services = RunningServices(url="http://127.0.0.1:8081", log_path=None, proc=None, config_path=None)

    with pytest.raises(pytest.UsageError, match="e2e_sidecars must be a mapping"):
        _start_config_sidecars(
            config_data={"e2e_sidecars": "authentik"},
            services=services,
            config_hash="abc123",
            runtime_root=tmp_path,
        )


def test_start_config_sidecars_rejects_non_mapping_authentik_config(tmp_path):
    services = RunningServices(url="http://127.0.0.1:8081", log_path=None, proc=None, config_path=None)

    with pytest.raises(pytest.UsageError, match=r"e2e_sidecars\.authentik must be a mapping"):
        _start_config_sidecars(
            config_data={"e2e_sidecars": {"authentik": "enabled"}},
            services=services,
            config_hash="abc123",
            runtime_root=tmp_path,
        )
