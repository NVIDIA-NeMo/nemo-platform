# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides for the Unsloth contributor."""

from __future__ import annotations

import typer

from nemo_customizer.shared.cli.job_json import apply_job_json_cli_overrides, make_load_job_json
from nemo_unsloth_plugin.schema import UnslothJobInput

_JOB_JSON_HELP = "Path to Unsloth job JSON (UnslothJobInput schema)."

load_job_json = make_load_job_json(UnslothJobInput)


def apply_unsloth_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``unsloth`` CLI: ``submit JOB.json``; ``run`` is disabled."""
    apply_job_json_cli_overrides(
        group,
        backend_name="unsloth",
        input_schema=UnslothJobInput,
        job_json_help=_JOB_JSON_HELP,
    )
