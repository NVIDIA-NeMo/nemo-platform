# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The agent entrypoint contract: one definition of what the evaluator imports.

Preflight resolves the same reference the evaluator imports, so it reports a
missing wrapper before a run instead of at the first trial. It must not import
``harbor`` to do so, because whether harbor is importable is itself a check.
"""

from importlib.machinery import PathFinder
from pathlib import Path

DEFAULT_AGENT_IMPORT_PATH = "harbor_wrapper:WrappedAgent"


def split_import_path(import_path: str) -> tuple[str, str]:
    """Split ``module:attribute``, the only form the evaluator can import."""
    module_name, _, attribute = import_path.partition(":")
    module_name = module_name.strip().lstrip(".")
    attribute = attribute.strip()
    if not module_name or not attribute:
        raise ValueError("import_path must be <module>:<attribute>")
    return module_name, attribute


def find_entrypoint_module(agent_dir: Path, module_name: str) -> Path | None:
    """Return the file the evaluator would import for *module_name*, or None.

    Searches *agent_dir* alone, as the evaluator's scoped import does, and never
    executes agent code.
    """
    search = [str(agent_dir)]
    origin: str | None = None
    for part in module_name.split("."):
        spec = PathFinder.find_spec(part, search)
        if spec is None:
            return None
        search = list(spec.submodule_search_locations or ())
        origin = spec.origin
    return Path(origin) if origin is not None else None
