# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nmp.core.models.controllers.backends.deployments_plugin.naming import entity_names


def test_entity_names_have_expected_suffixes() -> None:
    assert entity_names("my-dep").__dict__ == {
        "volume": "my-dep-weights",
        "puller": "my-dep-puller",
        "server": "my-dep-server",
    }
