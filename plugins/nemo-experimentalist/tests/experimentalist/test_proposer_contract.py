# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin the half of type reuse that lives in the prompt rather than the validator.

`CodeChangeProposer._run_with_context` is a CodeAct prompt, so its docstring is the
instruction the model follows. `_filter_improvements` accepting a repeated
`optimization_type` only stops the run from dying on one; if the prompt still
requires every type to be untried, the model never proposes one and the
allowance is unreachable. These tests keep the two halves in agreement.
"""

from __future__ import annotations

import inspect

from nemo_experimentalist_plugin.experimentalist.components.proposer import CodeChangeProposer


def _proposal_contract() -> str:
    """The prompt with whitespace collapsed, so assertions do not hinge on where it wraps."""
    doc = inspect.getdoc(CodeChangeProposer._run_with_context)
    assert doc is not None, "CodeChangeProposer._run_with_context must keep its docstring; it is the prompt"
    return " ".join(doc.lower().split())


def test_contract_permits_reusing_a_tried_type() -> None:
    """A hard `MUST be in available_types` makes reuse unreachable while any type is untried."""
    contract = _proposal_contract()
    assert "must be in `available_types` or" in contract, "the contract must not restrict the pick to untried types"
    assert "`tried_types`" in contract, "reuse is only reachable if tried types are a legal pick"


def test_contract_keeps_novelty_as_a_preference() -> None:
    """Reuse being legal must not make it the default; untried directions are still preferred."""
    contract = _proposal_contract()
    assert "prefer" in contract, "novelty has to survive as a preference, not vanish with the restriction"


def test_contract_does_not_restrict_the_card_pick_to_untried_types() -> None:
    """The per-improvement step would otherwise contradict the MANDATORY block."""
    contract = _proposal_contract()
    assert "pick one optimization_type from `available_types`" not in contract
