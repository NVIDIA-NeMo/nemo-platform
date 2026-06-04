# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides for the Automodel contributor."""

from __future__ import annotations

import typer

from nemo_customizer.shared.cli.job_json import apply_job_json_cli_overrides, make_load_job_json
from nemo_automodel_plugin.schema import AutomodelJobInput

_JOB_JSON_HELP = "Path to Automodel job JSON (AutomodelJobInput schema)."

load_job_json = make_load_job_json(AutomodelJobInput)


def apply_automodel_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``automodel`` CLI: ``submit JOB.json``; ``run`` is disabled."""
    apply_job_json_cli_overrides(
        group,
        backend_name="automodel",
        input_schema=AutomodelJobInput,
        job_json_help=_JOB_JSON_HELP,
    )
