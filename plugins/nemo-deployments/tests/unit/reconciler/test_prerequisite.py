# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from helpers import make_deployment
from nemo_deployments_plugin.entities import Prerequisite
from nemo_deployments_plugin.reconciler.prerequisite import prerequisites_met


def test_prerequisites_met_when_empty() -> None:
    dep = make_deployment()
    result = prerequisites_met(dep, deployments_by_name={})
    assert result.met is True


def test_prerequisites_waiting_for_missing() -> None:
    dep = make_deployment("server")
    dep.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    result = prerequisites_met(dep, deployments_by_name={})
    assert result.met is False
    assert result.blocking_prerequisite == "puller"
    assert "Waiting" in result.reason


def test_prerequisites_succeeded_condition() -> None:
    puller = make_deployment("puller")
    puller.status = "SUCCEEDED"
    puller.exit_code = 0
    server = make_deployment("server")
    server.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    by_name = {("default", "puller"): puller}
    result = prerequisites_met(server, deployments_by_name=by_name)
    assert result.met is True


def test_prerequisites_ready_condition() -> None:
    worker = make_deployment("worker")
    worker.status = "READY"
    server = make_deployment("server")
    server.prerequisites = [Prerequisite(deployment_name="worker", condition="ready")]
    by_name = {("default", "worker"): worker}
    result = prerequisites_met(server, deployments_by_name=by_name)
    assert result.met is True


def test_prerequisites_failed_propagation() -> None:
    puller = make_deployment("puller")
    puller.status = "FAILED"
    server = make_deployment("server")
    server.prerequisites = [Prerequisite(deployment_name="puller")]
    by_name = {("default", "puller"): puller}
    result = prerequisites_met(server, deployments_by_name=by_name)
    assert result.met is False
    assert "failed" in result.reason.lower()


def test_prerequisites_invalid_ref_stays_unmet() -> None:
    server = make_deployment("server")
    server.prerequisites = [Prerequisite(deployment_name="/bad")]
    result = prerequisites_met(server, deployments_by_name={})
    assert result.met is False
    assert "Invalid prerequisite ref" in result.reason


def test_prerequisites_resolve_by_deployment_name_not_config() -> None:
    """Prerequisite deployment_name must match the Deployment entity name."""
    puller = make_deployment("puller-run-1")
    puller.status = "SUCCEEDED"
    puller.exit_code = 0
    collision = make_deployment("puller")
    collision.deployment_config = "puller-run-1"
    collision.status = "PENDING"
    server = make_deployment("server")
    server.prerequisites = [Prerequisite(deployment_name="puller-run-1", condition="succeeded")]
    by_name = {("default", "puller"): collision, ("default", "puller-run-1"): puller}
    result = prerequisites_met(server, deployments_by_name=by_name)
    assert result.met is True
