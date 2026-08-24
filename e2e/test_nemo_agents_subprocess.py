# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for subprocess-mode agent deployments.

This module starts NeMo Platform through the subprocess E2E harness, deploys a
real agent as a child process through the agents plugin, and invokes it through
the agents gateway. The end-to-end chain is::

    sdk.agents.invoke (gateway proxy, subprocess endpoint resolution)
      -> NAT or Fabric agent child process
      -> Inference Gateway /openai (base_url injected at deploy time)
      -> mock provider short-circuit (no real upstream / no API key)
      -> response back through the gateway

Unlike the Docker and Kubernetes modules, this scenario needs neither a
prebuilt image nor an external cluster. The ``subprocess_only`` marker keeps it
in the standard Python E2E job and prevents it from running against an external
Platform, where this module's local harness configuration would be ignored.
"""

import pytest
from nemo_agents_plugin.entities import NAT_WORKFLOW_CONFIG_FORMAT, NEMO_AGENTS_SPEC_CONFIG_FORMAT
from nemo_platform_plugin.client.client import NemoClient

from e2e.agents_deploy_helpers import run_agent_deploy_and_invoke

pytestmark = [
    pytest.mark.subprocess_only,
    pytest.mark.e2e_config(
        "e2e/configs/local-subprocess.yaml",
        harness={"backend": "subprocess"},
    ),
]


def test_nat_agent_deploys_and_invokes_through_gateway(sdk: NemoClient, workspace: str) -> None:
    """Deploy a NAT agent as a subprocess and invoke it through the gateway."""
    run_agent_deploy_and_invoke(
        sdk,
        workspace=workspace,
        deployment_mode="subprocess",
        config_format=NAT_WORKFLOW_CONFIG_FORMAT,
    )


def test_fabric_agent_deploys_and_invokes_through_gateway(sdk: NemoClient, workspace: str) -> None:
    """Deploy a Fabric-backed agent as a subprocess and invoke it through the gateway."""
    run_agent_deploy_and_invoke(
        sdk,
        workspace=workspace,
        deployment_mode="subprocess",
        config_format=NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    )
