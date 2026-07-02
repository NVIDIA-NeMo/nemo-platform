# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_deployments_plugin.backends.labels import (
    k8s_deployment_resource_name,
    k8s_volume_resource_name,
    managed_by_label_selector,
)


def test_k8s_resource_names_match_docker_prefixes() -> None:
    dep = k8s_deployment_resource_name("foo", "bar-baz")
    vol = k8s_volume_resource_name("foo", "data")
    assert dep.startswith("dep-")
    assert vol.startswith("dep-vol-")
    assert len(dep) <= 63
    assert len(vol) <= 63


def test_ambiguous_workspace_name_pairs_get_distinct_k8s_names() -> None:
    a = k8s_deployment_resource_name("foo", "bar-baz")
    b = k8s_deployment_resource_name("foo-bar", "baz")
    assert a != b


def test_managed_by_label_selector() -> None:
    assert managed_by_label_selector() == "managed-by=nemo-deployments"
