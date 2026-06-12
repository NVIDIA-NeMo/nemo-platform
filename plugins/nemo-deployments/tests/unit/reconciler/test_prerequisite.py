# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from helpers import make_deployment, make_deployment_config
from nemo_deployments_plugin.entities import Prerequisite
from nemo_deployments_plugin.reconciler.prerequisite import prerequisites_met


def test_prerequisites_met_when_empty() -> None:
    dep = make_deployment()
    cfg = make_deployment_config()
    result = prerequisites_met(dep, cfg, deployments_by_config={}, deployments_by_name={})
    assert result.met is True


def test_prerequisites_waiting_for_missing() -> None:
    dep = make_deployment("server")
    cfg = make_deployment_config("server")
    cfg.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    result = prerequisites_met(dep, cfg, deployments_by_config={}, deployments_by_name={})
    assert result.met is False
    assert result.blocking_prerequisite == "puller"
    assert "Waiting" in result.reason


def test_prerequisites_succeeded_condition() -> None:
    puller = make_deployment("puller")
    puller.deployment_config = "puller"
    puller.status = "SUCCEEDED"
    puller.exit_code = 0
    server = make_deployment("server")
    cfg = make_deployment_config("server")
    cfg.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    by_name = {("default", "puller"): puller}
    by_config = {("default", "puller"): puller}
    result = prerequisites_met(server, cfg, deployments_by_config=by_config, deployments_by_name=by_name)
    assert result.met is True


def test_prerequisites_ready_condition() -> None:
    dep = make_deployment("worker")
    dep.status = "READY"
    server = make_deployment("server")
    cfg = make_deployment_config("server")
    cfg.prerequisites = [Prerequisite(deployment_name="worker", condition="ready")]
    by_name = {("default", "worker"): dep}
    by_config = {("default", "worker"): dep}
    result = prerequisites_met(server, cfg, deployments_by_config=by_config, deployments_by_name=by_name)
    assert result.met is True


def test_prerequisites_failed_propagation() -> None:
    puller = make_deployment("puller")
    puller.status = "FAILED"
    server = make_deployment("server")
    cfg = make_deployment_config("server")
    cfg.prerequisites = [Prerequisite(deployment_name="puller")]
    by_name = {("default", "puller"): puller}
    by_config = {("default", "puller"): puller}
    result = prerequisites_met(server, cfg, deployments_by_config=by_config, deployments_by_name=by_name)
    assert result.met is False
    assert "failed" in result.reason.lower()


def test_prerequisites_prefer_config_index_over_name_collision() -> None:
    """deployment_name is a DeploymentConfig name; do not match unrelated deployment names."""
    puller = make_deployment("puller")
    puller.deployment_config = "puller"
    puller.status = "SUCCEEDED"
    puller.exit_code = 0
    collision = make_deployment("puller")
    collision.deployment_config = "other-config"
    collision.status = "PENDING"
    server = make_deployment("server")
    cfg = make_deployment_config("server")
    cfg.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    by_name = {("default", "puller"): collision}
    by_config = {("default", "puller"): puller}
    result = prerequisites_met(server, cfg, deployments_by_config=by_config, deployments_by_name=by_name)
    assert result.met is True
