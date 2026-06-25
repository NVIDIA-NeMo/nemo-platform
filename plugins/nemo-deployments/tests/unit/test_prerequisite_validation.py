# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from helpers import make_deployment
from nemo_deployments_plugin.entities import Prerequisite
from nemo_deployments_plugin.validation import (
    PrerequisiteCycleError,
    build_existing_prerequisite_map,
    deployment_graph_key,
    detect_prerequisite_cycle,
    normalized_prerequisite_name,
    prerequisite_names,
)


def test_linear_prerequisites_ok() -> None:
    detect_prerequisite_cycle(
        deployment_name="default/c",
        prerequisites=["default/b"],
        existing={"default/a": [], "default/b": ["default/a"]},
    )


def test_self_cycle_rejected() -> None:
    with pytest.raises(PrerequisiteCycleError, match="cycle"):
        detect_prerequisite_cycle(
            deployment_name="default/a",
            prerequisites=["default/a"],
            existing={},
        )


def test_three_node_cycle_rejected() -> None:
    with pytest.raises(PrerequisiteCycleError):
        detect_prerequisite_cycle(
            deployment_name="default/a",
            prerequisites=["default/c"],
            existing={"default/b": ["default/a"], "default/c": ["default/b"]},
        )


def test_qualified_prerequisite_name_uses_workspace_prefix() -> None:
    assert normalized_prerequisite_name("default/foo", "default") == "default/foo"
    assert normalized_prerequisite_name("foo", "default") == "default/foo"
    assert normalized_prerequisite_name("other/foo", "default") == "other/foo"


def test_cycle_detected_when_existing_uses_qualified_same_workspace_ref() -> None:
    b = make_deployment("b")
    b.prerequisites = [Prerequisite(deployment_name="default/a")]
    existing = build_existing_prerequisite_map([b])
    with pytest.raises(PrerequisiteCycleError):
        detect_prerequisite_cycle(
            deployment_name=deployment_graph_key("default", "a"),
            prerequisites=[deployment_graph_key("default", "b")],
            existing=existing,
        )


def test_prerequisite_names_normalizes_for_create_validation() -> None:
    names = prerequisite_names([Prerequisite(deployment_name="default/puller")], "default")
    assert names == ["default/puller"]
