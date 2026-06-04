# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel customization contributor."""

from nemo_customizer.shared.contributor import ContributorBackendConfig, make_customization_contributor

from nemo_automodel_plugin.cli.inputs import apply_automodel_job_cli_overrides
from nemo_automodel_plugin.config import generate_automodel_id, get_config
from nemo_automodel_plugin.jobs.jobs import AutomodelJob

AutomodelContributor = make_customization_contributor(
    ContributorBackendConfig(
        name="automodel",
        tag="Automodel",
        cli_help="Automodel training jobs (SFT, distillation).",
        health_description="Automodel contributor health.",
        jobs_description="Automodel training jobs.",
        job_cls=AutomodelJob,
        generate_job_name=generate_automodel_id,
        get_config=get_config,
        apply_cli_overrides=apply_automodel_job_cli_overrides,
    ),
    class_name="AutomodelContributor",
)
