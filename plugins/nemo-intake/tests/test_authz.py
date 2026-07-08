# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authorization derivation for the Intake plugin."""

from __future__ import annotations

from nemo_intake_plugin.service import IntakeService
from nemo_platform_plugin.authz_discovery import _derive_service_contribution


def test_intake_authz_derivation_has_no_problems() -> None:
    contribution, problems, _warnings = _derive_service_contribution(IntakeService())
    assert problems == []

    assert {
        "intake.annotations.create",
        "intake.annotations.delete",
        "intake.annotations.list",
        "intake.annotations.read",
        "intake.evaluator-results.create",
        "intake.evaluator-results.list",
        "intake.evaluator-results.read",
        "intake.experiment-groups.create",
        "intake.experiment-groups.delete",
        "intake.experiment-groups.read",
        "intake.experiment-groups.update",
        "intake.experiments.create",
        "intake.experiments.delete",
        "intake.experiments.read",
        "intake.experiments.update",
        "intake.ingest.create",
        "intake.spans.list",
        "intake.spans.read",
        "intake.traces.read",
    } <= set(contribution.permissions)

    annotations = contribution.endpoints["/apis/intake/v2/workspaces/{workspace}/annotations"]
    assert annotations["get"].permissions == ["intake.annotations.list"]
    assert annotations["get"].scopes == ["intake:read", "platform:read"]
    assert annotations["post"].permissions == ["intake.annotations.create"]
    assert annotations["post"].scopes == ["intake:write", "platform:write"]

    ingest = contribution.endpoints["/apis/intake/v2/workspaces/{workspace}/ingest/atif"]
    assert ingest["post"].permissions == ["intake.ingest.create"]

    for methods in contribution.endpoints.values():
        for binding in methods.values():
            assert binding.deny is False
