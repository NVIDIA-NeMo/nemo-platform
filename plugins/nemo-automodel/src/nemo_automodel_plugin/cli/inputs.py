# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides for the Automodel contributor.

The override machinery is shared in :mod:`nmp.customization_common.cli.overrides`; this
module supplies the Automodel specifics: the ``AutomodelJobInput`` schema (via
``load_job_json``), the ``JOB_JSON`` help text, and the run-disabled message.
"""

import json
from pathlib import Path

import typer
from nmp.customization_common.cli.overrides import apply_job_cli_overrides

from nemo_automodel_plugin.schema import AutomodelJobInput

_JOB_JSON_HELP = "Path to Automodel job JSON (AutomodelJobInput schema)."
_RUN_DISABLED_MESSAGE = (
    "Automodel does not support local run. Submit to the platform API instead:\n"
    "  nemo customization automodel submit <job.json> -w <workspace>"
)


def load_job_json(path: Path) -> str:
    """Load and validate job JSON; return canonical JSON string for ``--spec``."""
    data = json.loads(path.read_text())
    validated = AutomodelJobInput.model_validate(data)
    return validated.model_dump_json()


def apply_automodel_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``automodel`` CLI: ``submit JOB.json``; ``run`` is disabled."""
    apply_job_cli_overrides(
        group,
        load_job_json=load_job_json,
        job_json_help=_JOB_JSON_HELP,
        run_disabled_message=_RUN_DISABLED_MESSAGE,
    )
