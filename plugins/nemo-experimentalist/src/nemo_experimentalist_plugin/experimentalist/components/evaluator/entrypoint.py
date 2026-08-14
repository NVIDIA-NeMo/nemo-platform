# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The agent entrypoint contract: one definition of what the evaluator imports.

The evaluator imports ``import_path`` from the candidate agent directory and
nothing else. Preflight resolves the same reference against the agent source so
a missing wrapper is reported before a run instead of at the first trial. Both
sides read this module, so they cannot disagree.

Importable in the CLI hot path: standard library only, no ``harbor``.
"""

from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path

DEFAULT_AGENT_IMPORT_PATH = "harbor_wrapper:WrappedAgent"


def split_import_path(import_path: str) -> tuple[str, str]:
    """Split ``module[:attribute]`` into its normalized module and attribute."""
    module_name, _, attribute = import_path.partition(":")
    module_name = module_name.strip().lstrip(".")
    if not module_name:
        raise ValueError("import_path module is required")
    return module_name, attribute.strip()


def find_entrypoint_module(agent_dir: Path, module_name: str) -> Path | None:
    """Return the file the evaluator would import for *module_name*, or None.

    Searches *agent_dir* alone, as the evaluator's scoped import does, and never
    executes agent code.
    """
    search = [str(agent_dir)]
    spec: ModuleSpec | None = None
    for part in module_name.split("."):
        spec = PathFinder.find_spec(part, search)
        if spec is None:
            return None
        search = list(spec.submodule_search_locations or ())
    return Path(spec.origin) if spec is not None and spec.origin is not None else None
