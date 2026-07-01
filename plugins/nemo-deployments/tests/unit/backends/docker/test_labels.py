# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for deployment identity labels."""

from __future__ import annotations

import re

from nemo_deployments_plugin.backends.docker.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    container_name,
    deployment_identity_labels,
    docker_volume_name,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_platform_plugin.k8s_naming import k8s_safe_name

_HASH8 = re.compile(r"-[0-9a-f]{8}$")
_DNS_LABEL = re.compile(r"^[a-z](?:[a-z0-9-]*[a-z0-9])?$")


def _assert_dns_label_safe(name: str) -> None:
    assert len(name) <= 63
    assert _DNS_LABEL.fullmatch(name)
    assert _HASH8.search(name)


def test_container_name_is_dns_safe() -> None:
    name = container_name("my-workspace", "my.deployment")
    assert name.startswith("dep-")
    _assert_dns_label_safe(name)


def test_k8s_safe_name_always_includes_hash_suffix() -> None:
    name = k8s_safe_name("short-name")
    assert _HASH8.search(name)
    assert name == k8s_safe_name("short-name")


def test_container_name_ambiguous_workspace_name_pairs_differ() -> None:
    name_a = container_name("foo", "bar-baz")
    name_b = container_name("foo-bar", "baz")
    assert name_a != name_b
    _assert_dns_label_safe(name_a)
    _assert_dns_label_safe(name_b)


def test_docker_volume_name_ambiguous_workspace_name_pairs_differ() -> None:
    name_a = docker_volume_name("foo", "bar-baz")
    name_b = docker_volume_name("foo-bar", "baz")
    assert name_a != name_b
    assert name_a.startswith("dep-vol-")
    assert name_b.startswith("dep-vol-")
    _assert_dns_label_safe(name_a)
    _assert_dns_label_safe(name_b)


def test_k8s_safe_name_empty_base_uses_fallback_prefix() -> None:
    name = k8s_safe_name("")
    assert name.startswith("x-")
    assert len(name) <= 63


def test_docker_volume_name_prefix() -> None:
    assert docker_volume_name("ws", "vol").startswith("dep-vol-")


def test_deployment_identity_labels() -> None:
    labels = deployment_identity_labels(
        "default",
        "srv",
        "Always",
        config_name="cfg1",
    )
    assert labels[MANAGED_BY_KEY] == MANAGED_BY_LABEL
    assert labels[DEPLOYMENT_WORKSPACE_LABEL] == "default"
    assert labels[DEPLOYMENT_NAME_LABEL] == "srv"
    assert labels[CONFIG_NAME_LABEL] == "cfg1"
