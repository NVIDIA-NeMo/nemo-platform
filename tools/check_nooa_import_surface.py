#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check that the installed `nooa` provides every symbol the plugins import.

`nooa` is a pre-1.0 dependency that moved from a git pin to a PyPI floor, so a
resolver is free to pick up a release that dropped or renamed something the
plugins reach for. Import errors from that surface only appear when the specific
module is first imported, which for agent components can be deep into a run.
This walks the imports statically instead and reports the whole gap at once.

    uv run python tools/check_nooa_import_surface.py

Exits non-zero when something is missing. This checks names, not behaviour --
a symbol that kept its name but changed semantics still needs the test suites.
"""

import argparse
import ast
import importlib
import pathlib
import sys

PLUGIN_SOURCE_ROOTS = (
    "plugins/nemo-insights/src",
    "plugins/nemo-experimentalist/src",
    "plugins/nemo-eval-author/src",
)


def collect_imports(roots: tuple[str, ...], repo_root: pathlib.Path) -> dict[str, set[str]]:
    """Map each imported `nooa` module to the set of names taken from it."""
    imported: dict[str, set[str]] = {}
    for root in roots:
        for path in sorted((repo_root / root).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                print(f"warning: skipping {path} ({exc})", file=sys.stderr)
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module and node.module.split(".")[0] == "nooa":
                        imported.setdefault(node.module, set()).update(alias.name for alias in node.names)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] == "nooa":
                            imported.setdefault(alias.name, set())
    return imported


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of tools/).",
    )
    args = parser.parse_args()

    try:
        nooa = importlib.import_module("nooa")
    except ImportError as exc:
        print(f"FAIL: cannot import nooa: {exc}")
        print("Install the workspace first: uv sync --all-packages")
        return 1

    version = getattr(nooa, "__version__", "unknown")
    imported = collect_imports(PLUGIN_SOURCE_ROOTS, args.repo_root)
    print(f"installed nooa: {version}")
    print(f"checking {sum(len(v) for v in imported.values())} names across {len(imported)} modules")

    missing: list[str] = []
    for module_name in sorted(imported):
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            missing.append(f"{module_name} (module missing: {exc})")
            continue
        for symbol in sorted(imported[module_name]):
            if symbol != "*" and not hasattr(module, symbol):
                missing.append(f"{module_name}.{symbol}")

    if missing:
        print(f"\nFAIL: {len(missing)} missing:")
        for item in missing:
            print(f"  - {item}")
        return 1

    print("\nOK: every imported nooa name resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
