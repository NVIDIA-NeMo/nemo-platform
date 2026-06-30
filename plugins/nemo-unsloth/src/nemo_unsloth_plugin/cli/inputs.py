# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides for the Unsloth contributor.

The override machinery is shared in :mod:`nmp.customization_common.cli.overrides`; this
module supplies the Unsloth specifics: the ``UnslothJobInput`` schema (via
``load_job_json``), the ``JOB_JSON`` help text, and the run-disabled message.
"""

import json
from pathlib import Path

import typer
from nmp.customization_common.cli.overrides import apply_job_cli_overrides

from nemo_unsloth_plugin.schema import UnslothJobInput

_JOB_JSON_HELP = "Path to Unsloth job JSON (UnslothJobInput schema)."
_RUN_DISABLED_MESSAGE = (
    "Unsloth does not support local run. Submit to the platform API instead:\n"
    "  nemo customization unsloth submit <job.json> -w <workspace>"
)


def load_job_json(path: Path) -> str:
    """Load and validate job JSON; return canonical JSON string for ``--spec``."""
    data = json.loads(path.read_text())
    validated = UnslothJobInput.model_validate(data)
    return validated.model_dump_json()


def apply_unsloth_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``unsloth`` CLI: ``submit JOB.json``; ``run`` is disabled."""
    apply_job_cli_overrides(
        group,
        load_job_json=load_job_json,
        job_json_help=_JOB_JSON_HELP,
        run_disabled_message=_RUN_DISABLED_MESSAGE,
    )
