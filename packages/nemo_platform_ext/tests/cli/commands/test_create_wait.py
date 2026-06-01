# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import typer

# from nemo_platform_ext.cli.commands.api.customization.jobs import create_jobs as create_customization_job
from nemo_platform_ext.cli.commands.api.inference.deployments import create_deployments


def _ctx(client: object) -> SimpleNamespace:
    state = MagicMock()
    state.agent_mode = False
    state.get_client.return_value = client
    state.get_output_format.return_value = None
    state.get_no_truncate.return_value = False
    state.get_timestamp_format.return_value = None
    return SimpleNamespace(obj=state)


# def test_customization_job_create_waits_for_created_job() -> None:
#     jobs = MagicMock()
#     jobs.create.return_value = SimpleNamespace(name="created-job")
#     client = SimpleNamespace(customization=SimpleNamespace(jobs=jobs))
#     ctx = _ctx(client)

#     with (
#         patch(
#             "nemo_platform_ext.cli.commands.api.customization.jobs.handle_code_generation",
#             return_value=False,
#         ) as handle_code_generation,
#         patch("nemo_platform_ext.cli.commands.api.customization.jobs.format_output"),
#         patch(
#             "nemo_platform_ext.cli.commands.api.customization.jobs.wait_for_platform_job",
#             return_value=True,
#         ) as wait_for_platform_job,
#     ):
#         create_customization_job(
#             ctx,
#             name="input-job",
#             workspace="test-workspace",
#             spec='{"training_type": "sft"}',
#             wait=True,
#             timeout=42,
#             poll_interval=7,
#         )

#     handle_code_generation.assert_called_once_with(
#         ["customization", "jobs"],
#         "create",
#         {"workspace": "test-workspace", "spec": {"training_type": "sft"}, "name": "input-job"},
#         None,
#         ctx.obj,
#         wait_config={"type": "platform_job", "resource_label": "customization job"},
#         wait_options={"timeout": 42, "poll_interval": 7},
#     )
#     jobs.create.assert_called_once_with(
#         workspace="test-workspace",
#         spec={"training_type": "sft"},
#         name="input-job",
#     )
#     wait_for_platform_job.assert_called_once_with(
#         jobs,
#         "created-job",
#         workspace="test-workspace",
#         resource_label="customization job",
#         timeout=42,
#         poll_interval=7,
#     )


def test_inference_deployment_create_exits_when_wait_fails() -> None:
    deployments = MagicMock()
    deployments.create.return_value = SimpleNamespace(name="deployment-a")
    client = SimpleNamespace(inference=SimpleNamespace(deployments=deployments))

    with (
        patch("nemo_platform_ext.cli.commands.api.inference.deployments.handle_code_generation", return_value=False),
        patch("nemo_platform_ext.cli.commands.api.inference.deployments.format_output"),
        patch(
            "nemo_platform_ext.cli.commands.api.inference.deployments.wait_for_inference_deployment",
            return_value=False,
        ) as wait_for_inference_deployment,
        pytest.raises(typer.Exit) as exc_info,
    ):
        create_deployments(
            _ctx(client),
            name="deployment-a",
            workspace="test-workspace",
            config="deployment-config",
            wait=True,
            timeout=90,
            poll_interval=10,
        )

    assert exc_info.value.exit_code == 1
    wait_for_inference_deployment.assert_called_once_with(
        client,
        "deployment-a",
        workspace="test-workspace",
        timeout=90,
        poll_interval=10,
    )
