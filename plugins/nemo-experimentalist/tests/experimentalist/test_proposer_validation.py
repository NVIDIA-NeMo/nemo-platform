# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What the Proposer must reject before its output reaches a Builder.

`ancestor` became a candidate id rather than a display handle, and survivors are handed
to the model carrying both — so a plausible-looking `"agent-2"` is exactly what comes
back. One rejected batch costs a retry; an unvalidated one costs the run, because the
fork that resolves it happens outside the per-proposal error handling.
"""

import pytest
from nemo_experimentalist_plugin.experimentalist.components.proposer import Improvement, Proposer


def _improvement(ancestor: str) -> Improvement:
    return Improvement(
        ancestor=ancestor,
        optimization="add a retrieval step",
        root_cause="the agent never retrieves",
        optimization_type="add_method",
        task_ids=["task-1"],
    )


def test_an_ancestor_that_is_not_a_survivor_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown ancestor"):
        Proposer._validate_improvements(
            improvements=[_improvement("agent-2")],
            max_candidates=3,
            allowed_types={"add_method"},
            known_ancestors={"id-agent-2"},
        )


def test_a_real_survivor_id_passes() -> None:
    Proposer._validate_improvements(
        improvements=[_improvement("id-agent-2")],
        max_candidates=3,
        allowed_types={"add_method"},
        known_ancestors={"id-agent-2"},
    )
