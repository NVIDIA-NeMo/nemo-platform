# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The Experimentalist's terminal result — a pure, storage-agnostic summary.

:class:`ExperimentalistResult` is ephemeral: its data is unpacked into
:class:`~nemo_experimentalist_plugin.entities.ExperimentRun` and
:class:`~nemo_experimentalist_plugin.entities.Candidate` via
``backend.persist_result()``. It is fully recoverable from entity store
queries after a completed run.
"""

from nemo_experimentalist_plugin.entities import Candidate
from pydantic import BaseModel, Field


class ExperimentalistResult(BaseModel):
    """Ephemeral output of one Experimentalist run.

    Passed to ``backend.persist_result()`` which writes it into the entity
    store (ExperimentRun status/summary + winner Candidate id). All fields
    are recoverable from entity queries after persistence.
    """

    summary: str = Field(
        min_length=1,
        description=(
            "Brief natural-language summary of the optimization run and its "
            "outcome, for the developer reading the result."
        ),
    )
    run_id: str = Field(
        min_length=1,
        description="ExperimentRun entity id updated by persist_result.",
    )
    rounds_completed: int = Field(
        ge=0,
        description="Number of full optimization rounds that ran.",
    )
    winner: Candidate | None = Field(
        default=None,
        description=(
            "The best candidate from the run (highest validation reward). "
            "None when no candidate outperformed the baseline."
        ),
    )
