# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail: Intake publishing must use the slim client boundary.

The mapping and publisher may import ``nemo_intake_client``, but must not reach
into the Intake service implementation or raw HTTP transport.
"""

from __future__ import annotations

import re
from importlib.metadata import requires
from pathlib import Path

import nemo_evaluator.intake as intake

INTAKE_ROOT = Path(next(iter(intake.__path__))).resolve()

# Imports that bypass the plugin-owned client contract.
_FORBIDDEN = re.compile(r"^\s*(?:from|import)\s+(nemo_intake_plugin|nmp\.intake|nmp_intake|httpx)", re.MULTILINE)


def test_intake_mapping_has_no_service_imports() -> None:
    offenders: list[str] = []
    for path in sorted(INTAKE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _FORBIDDEN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(INTAKE_ROOT)}:{line_no}: {match.group(0).strip()}")

    assert not offenders, (
        "nemo_evaluator.intake must use nemo_intake_client instead of service or HTTP imports:\n" + "\n".join(offenders)
    )


def test_evaluator_depends_on_slim_intake_client_only() -> None:
    dependency_names = {
        match.group(0).lower().replace("_", "-")
        for value in requires("nemo-evaluator-plugin") or []
        if (match := re.match(r"[A-Za-z0-9_.-]+", value)) is not None
    }

    assert "nemo-intake-client" in dependency_names
    assert "nemo-intake-plugin" not in dependency_names
