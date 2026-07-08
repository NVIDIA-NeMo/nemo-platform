# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail: Intake publishing must use the plugin client boundary.

The mapping and publisher may import Intake's plugin-owned schemas and client,
but must not reach into the legacy service package or raw HTTP transport.
"""

from __future__ import annotations

import re
from pathlib import Path

import nemo_evaluator.intake as intake

INTAKE_ROOT = Path(next(iter(intake.__path__))).resolve()

# Imports that bypass the plugin-owned client contract.
_FORBIDDEN = re.compile(r"^\s*(?:from|import)\s+(nmp\.intake|nmp_intake|httpx)", re.MULTILINE)


def test_intake_mapping_has_no_service_imports() -> None:
    offenders: list[str] = []
    for path in sorted(INTAKE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _FORBIDDEN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(INTAKE_ROOT)}:{line_no}: {match.group(0).strip()}")

    assert not offenders, "nemo_evaluator.intake must not import legacy Intake or raw HTTP:\n" + "\n".join(offenders)
