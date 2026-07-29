# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ratchet on Eval Author's remaining dependency on Experimentalist.

Eval Author is meant to end up standalone, with Experimentalist depending on it and not the
other way around. Until then this test pins the modules Eval Author still reaches for, so
the coupling can only shrink. Prefer duplicating a helper over adding a row here.

Emptying the allowlist is what unblocks the TODO(eval-author-standalone) cleanups: the
``EXPERIMENTALIST_*`` credential fallback and the ``_env_bridge`` side-effect module both
exist only to serve the imports listed below.
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "nemo_eval_author_plugin"

# Each entry is the module named in the import statement, so `from ...components import
# cache` is recorded as `...components`. Each one is debt: deleting a row is the goal, and
# adding a row needs a deliberate argument for why duplicating the helper is worse. What
# Eval Author still borrows, by row:
#
#   client              -> make_client, the platform client factory
#   ...components       -> the cache module, for run artifacts
#   ...dataset_staging  -> stage_task_template
#   ...evaluator        -> Dataset / Task / TrialResult / DatasetValidationError
#   ...evaluator.base   -> EvaluatorType
#   ...evaluator.factory-> DatasetFactory
#   ...evaluator.harbor -> HarborDataset
#   ...evaluator.models -> DatasetRef, ResourceRef, Task, local_path_from_uri
#   ...tools            -> GuardedShellTools
#   ...trace_analyzer   -> TraceAnalyzer, TraceAnalyzerConfig, Diagnostic
#   ...trace_explorer   -> TraceExplorer and its view models
#   experimentalist_backend -> make_experimentalist_backend
_ALLOWED_EXPERIMENTALIST_IMPORTS = {
    "nemo_experimentalist_plugin.client",
    "nemo_experimentalist_plugin.experimentalist.components",
    "nemo_experimentalist_plugin.experimentalist.components.dataset_staging",
    "nemo_experimentalist_plugin.experimentalist.components.evaluator",
    "nemo_experimentalist_plugin.experimentalist.components.evaluator.base",
    "nemo_experimentalist_plugin.experimentalist.components.evaluator.factory",
    "nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor",
    "nemo_experimentalist_plugin.experimentalist.components.evaluator.models",
    "nemo_experimentalist_plugin.experimentalist.components.tools",
    "nemo_experimentalist_plugin.experimentalist.components.trace_analyzer",
    "nemo_experimentalist_plugin.experimentalist.components.trace_explorer",
    "nemo_experimentalist_plugin.experimentalist.experimentalist_backend",
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

    added = set(found) - _ALLOWED_EXPERIMENTALIST_IMPORTS
    assert not added, (
        "New Experimentalist imports in the Eval Author plugin: "
        + ", ".join(f"{name} (in {', '.join(sorted(found[name]))})" for name in sorted(added))
        + ". Eval Author is moving toward standalone, so duplicate the helper instead of "
        "importing it. If the import is genuinely unavoidable, add it to "
        "_ALLOWED_EXPERIMENTALIST_IMPORTS with a note explaining why."
    )

    removed = _ALLOWED_EXPERIMENTALIST_IMPORTS - set(found)
    assert not removed, (
        "These Experimentalist imports are gone, which is the point: "
        + ", ".join(sorted(removed))
        + ". Drop them from _ALLOWED_EXPERIMENTALIST_IMPORTS so the list keeps meaning something."
    )


def test_model_config_is_already_standalone() -> None:
    """Credential resolution is the one part of the plugin that owes Experimentalist nothing.

    It was briefly refactored to share Experimentalist's client cache, which read as a
    cleanup but moved the plugin away from standalone. Keep it independent.
    """
    importers = {file for files in _imported_experimentalist_modules().values() for file in files}

    assert "model_config.py" not in importers
