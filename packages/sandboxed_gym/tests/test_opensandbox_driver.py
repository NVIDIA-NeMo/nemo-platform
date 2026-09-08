# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the OpenSandbox episode driver's translation layer.

The driver replaces NeMo-Gym's 1541-line provider with the seven operations the episode backend
actually uses. Provisioning a real sandbox needs a cluster, so what is covered here is the part
that carries judgement and would otherwise be unverified: how typed resources, exec identity,
command output and lifecycle status map onto the SDK's shapes.
"""

from __future__ import annotations

import pytest
from sandboxed_gym.backends._opensandbox_driver import (
    _STATUS_ALIASES,
    _exec_identity,
    _joined_output,
    _resource_requests,
)
from sandboxed_gym.backends.base import UnsupportedEpisodeOperationError
from sandboxed_gym.sandbox_types import SandboxResources, SandboxSpec, SandboxStatus


def spec_with(**resources: object) -> SandboxSpec:
    return SandboxSpec(image="img:1", resources=SandboxResources(**resources))  # ty: ignore[invalid-argument-type]


def test_resources_map_onto_the_sdk_kubernetes_style_strings() -> None:
    # The SDK documents this format: cpu in millicores, memory with a binary suffix, gpu as a
    # count. Fractional CPU is the case worth pinning -- 0.5 cores is 500m, not "0.5".
    requests = _resource_requests(spec_with(cpu=0.5, memory_mib=2048, disk_gib=10, gpu=2))

    assert requests == {"cpu": "500m", "memory": "2048Mi", "ephemeral-storage": "10Gi", "gpu": "2"}


def test_unset_resources_are_omitted_rather_than_sent_as_zero() -> None:
    # A zero request is not the same as no request: it would pin the episode to nothing.
    assert _resource_requests(spec_with()) == {}


def test_a_gpu_type_request_is_refused_rather_than_dropped() -> None:
    """There is no documented request key for a device model.

    Dropping it silently would grade the episode on whatever GPU it happened to land on, which is
    the downgrade the backend contract forbids.
    """
    with pytest.raises(UnsupportedEpisodeOperationError, match="GPU type"):
        _resource_requests(spec_with(gpu=1, gpu_type="a100"))


@pytest.mark.parametrize(("user", "expected"), [(None, {}), (1000, {"uid": 1000}), ("1000", {"uid": 1000})])
def test_numeric_users_reach_the_sdk_as_a_uid(user: str | int | None, expected: dict[str, int]) -> None:
    assert _exec_identity(user) == expected


def test_a_named_user_is_refused_rather_than_guessed() -> None:
    # Resolving a name needs the image's passwd database; running as the wrong id is a silent
    # privilege change either way.
    with pytest.raises(UnsupportedEpisodeOperationError, match="numeric uid"):
        _exec_identity("root")


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


def test_output_messages_are_joined_into_one_stream() -> None:
    assert _joined_output([_Message("line one\n"), _Message("line two\n")]) == "line one\nline two\n"


@pytest.mark.parametrize("empty", [None, [], [_Message("")]])
def test_absent_output_is_none_not_an_empty_string(empty: object) -> None:
    # The contract's `stdout`/`stderr` are optional, and callers distinguish "no output" from
    # "empty output" when deciding whether a command said anything.
    assert _joined_output(empty) is None


def test_every_status_alias_maps_onto_a_real_contract_status() -> None:
    # The alias table exists because the SDK's vocabulary is wider than the contract's. A typo
    # here would resolve to UNKNOWN at runtime and look like a dead sandbox.
    assert all(isinstance(value, SandboxStatus) for value in _STATUS_ALIASES.values())
    assert "running" not in _STATUS_ALIASES, "statuses that already match must not be aliased"
