# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ratchet on Eval Author's remaining dependency on Experimentalist.

Two lists, because "imports Experimentalist" is not one thing.

``_SHARED_LAYER_A`` is the entity contract — ``Dataset``, ``Task``, ``TrialResult``,
``DatasetRef`` and friends. Every plugin is *supposed* to speak these; duplicating them
would fork the contract and break comparability in Studio. This list does not shrink.

``_BORROWED_BEHAVIOUR`` is debt, and it can only shrink. Duplicating a helper beats
adding a row.

Most of that debt came from the agent package. The agent moved into
``nemo_experimentalist_plugin.eval_author``, next to the evaluator, trace, and reporting
helpers it borrowed, so those borrows are now ordinary intra-package imports and the list
is down to the platform client that ``discovery/`` uses.
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "nemo_eval_author_plugin"

# Layer A: the shared entity contract. Permanent by design, not debt.
_SHARED_LAYER_A = {
    "nemo_experimentalist_plugin.entities",
}

# Behaviour Eval Author still borrows. Each row is debt; deleting one is the goal, and
# adding one needs a deliberate argument for why duplicating the helper is worse.
#
#   client -> make_client, the platform client factory that discovery/ builds on
_BORROWED_BEHAVIOUR = {
    "nemo_experimentalist_plugin.client",
}


def _imported_experimentalist_modules() -> dict[str, set[str]]:
    """Map each Experimentalist module imported under ``src`` to the files importing it."""
    found: dict[str, set[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # level > 0 is a relative import, which cannot reach another distribution.
                names = [node.module] if node.module and not node.level else []
            else:
                continue
            for name in names:
                if name.split(".")[0] == "nemo_experimentalist_plugin":
                    found.setdefault(name, set()).add(path.name)
    return found


def test_experimentalist_imports_only_shrink() -> None:
    found = _imported_experimentalist_modules()
    allowed = _SHARED_LAYER_A | _BORROWED_BEHAVIOUR

    added = set(found) - allowed
    assert not added, (
        "New Experimentalist imports in the Eval Author plugin: "
        + ", ".join(f"{name} (in {', '.join(sorted(found[name]))})" for name in sorted(added))
        + ". Eval Author is moving toward standalone, so duplicate the helper instead of "
        "importing it. If it is Layer A, add it to _SHARED_LAYER_A; if the borrow is "
        "genuinely unavoidable, add it to _BORROWED_BEHAVIOUR with a note explaining why."
    )

    removed = _BORROWED_BEHAVIOUR - set(found)
    assert not removed, (
        "These borrowed Experimentalist modules are gone, which is the point: "
        + ", ".join(sorted(removed))
        + ". Drop them from _BORROWED_BEHAVIOUR so the list keeps meaning something."
    )
