# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail: Intake publishing must use the slim client boundary.

The mapping and publisher may import ``nemo_intake_client``, but must not reach
into the Intake service implementation or raw HTTP transport.
"""

from __future__ import annotations

import ast
import re
from importlib.metadata import requires
from pathlib import Path

import nemo_evaluator.intake as intake

INTAKE_ROOT = Path(next(iter(intake.__path__))).resolve()

_FORBIDDEN_MODULES = ("nemo_intake_plugin", "nmp.intake", "nmp_intake", "httpx")


def _is_forbidden_module(module: str) -> bool:
    return any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in _FORBIDDEN_MODULES)


def _forbidden_imports(source: str) -> list[tuple[int, str]]:
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
            if not _is_forbidden_module(node.module):
                modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
        else:
            continue

        offenders.extend((node.lineno, module) for module in modules if _is_forbidden_module(module))
    return offenders


def test_intake_mapping_has_no_service_imports() -> None:
    offenders: list[str] = []
    for path in sorted(INTAKE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for line_no, _module in _forbidden_imports(text):
            offenders.append(f"{path.relative_to(INTAKE_ROOT)}:{line_no}: {lines[line_no - 1].strip()}")

    assert not offenders, (
        "nemo_evaluator.intake must use nemo_intake_client instead of service or HTTP imports:\n" + "\n".join(offenders)
    )


def test_forbidden_import_detection_handles_bypass_syntax() -> None:
    source = "import os, httpx\nfrom nmp import intake\nfrom nemo_intake_plugin.spans import service\n"

    assert _forbidden_imports(source) == [
        (1, "httpx"),
        (2, "nmp.intake"),
        (3, "nemo_intake_plugin.spans"),
    ]


def test_evaluator_depends_on_slim_intake_client_only() -> None:
    dependency_names = {
        match.group(0).lower().replace("_", "-")
        for value in requires("nemo-evaluator-plugin") or []
        if (match := re.match(r"[A-Za-z0-9_.-]+", value)) is not None
    }

    assert "nemo-intake-client" in dependency_names
    assert "nemo-intake-plugin" not in dependency_names
