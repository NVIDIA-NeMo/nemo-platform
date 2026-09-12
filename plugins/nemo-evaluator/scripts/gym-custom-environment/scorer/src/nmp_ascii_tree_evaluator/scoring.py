# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FileSet-delivered reward functions for the ASCII Tree example.

``prepare.py`` packages this module into a wheel. Gym installs that wheel in the
OpenSandbox runtime because the resources server declares it in
``requirements.txt``. The resources server then calls ``ascii_tree_reward()``
for each model response. The formulas preserve Prime Intellect ASCII Tree 0.1.5
semantics while remaining independent of its unsupported ``verifiers`` runtime.
"""

from __future__ import annotations

import difflib
import re

_ASCII_FORMATTED = re.compile(
    r"<ascii_formatted>\s*(.*?)\s*</ascii_formatted>",
    flags=re.DOTALL,
)


def extract_ascii_formatted(text: str) -> str | None:
    """Return the first ``ascii_formatted`` payload, or ``None`` when absent."""
    match = _ASCII_FORMATTED.search(text)
    if match is None:
        return None
    parsed_tree = match.group(1).strip()
    return parsed_tree or None


def _format_multiplier(lines: list[str]) -> float:
    """Apply indentation and tree-branch formatting penalties."""
    multiplier = 1.0
    if not all(line.startswith(" ") or line.rstrip() == lines[0] for line in lines[1:]):
        multiplier *= 0.5
    if not any("--" in line for line in lines[1:]):
        multiplier *= 0.5
    return multiplier


def similarity_reward(completion: str, answer: str) -> float:
    """Score whole-sequence line similarity with ASCII formatting penalties."""
    parsed_tree = extract_ascii_formatted(completion)
    if parsed_tree is None or not answer.strip():
        return 0.0

    try:
        completion_lines = parsed_tree.split("\n")
        expected_lines = answer.strip().split("\n")
        similarity = difflib.SequenceMatcher(
            None,
            completion_lines,
            expected_lines,
        ).ratio()
        return similarity * _format_multiplier(completion_lines)
    except Exception:
        # A malformed model response should receive zero reward, not crash the Gym run.
        return 0.0


def continuous_reward(completion: str, answer: str) -> float:
    """Score the longest contiguous line match with formatting penalties."""
    parsed_tree = extract_ascii_formatted(completion)
    if parsed_tree is None or not answer.strip():
        return 0.0

    try:
        completion_lines = parsed_tree.split("\n")
        expected_lines = answer.strip().split("\n")
        matcher = difflib.SequenceMatcher(None, completion_lines, expected_lines)
        longest_block = max(
            matcher.get_matching_blocks(),
            key=lambda block: block.size,
            default=difflib.Match(0, 0, 0),
        )
        contiguous_fraction = longest_block.size / len(expected_lines)
        return contiguous_fraction * _format_multiplier(completion_lines)
    except Exception:
        # Preserve the source environment's fail-closed scoring behavior.
        return 0.0


def ascii_tree_reward(completion: str, answer: str) -> float:
    """Combine global similarity (30%) and contiguous matching (70%)."""
    return 0.3 * similarity_reward(completion, answer) + 0.7 * continuous_reward(
        completion,
        answer,
    )
