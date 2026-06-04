# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth customization contributor."""

from nemo_customizer.shared.contributor import ContributorBackendConfig, make_customization_contributor

from nemo_unsloth_plugin.cli.inputs import apply_unsloth_job_cli_overrides
from nemo_unsloth_plugin.config import generate_unsloth_id, get_config
from nemo_unsloth_plugin.jobs.jobs import UnslothJob

UnslothContributor = make_customization_contributor(
    ContributorBackendConfig(
        name="unsloth",
        tag="Unsloth",
        cli_help="Unsloth GPU fine-tuning (container submit). SFT only.",
        health_description="Unsloth contributor health.",
        jobs_description="Unsloth GPU fine-tuning jobs (container submit).",
        job_cls=UnslothJob,
        generate_job_name=generate_unsloth_id,
        get_config=get_config,
        apply_cli_overrides=apply_unsloth_job_cli_overrides,
    ),
    class_name="UnslothContributor",
)
