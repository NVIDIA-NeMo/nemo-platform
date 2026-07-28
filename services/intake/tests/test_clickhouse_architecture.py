# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Import-boundary tests for Intake ClickHouse persistence."""

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "nmp" / "intake"
_RAW_CLIENT_MODULE = "nmp.intake.spans.clickhouse_client"

# Shrink this allowlist as each legacy repository moves behind ClickHouseExecutor.
_ALLOWED_RAW_CLIENT_IMPORTS = {
    "api/v2/experiments/dependencies.py",
    "repository/clickhouse/executor.py",
    "service.py",
    "spans/api/dependencies.py",
}


def test_raw_clickhouse_client_imports_are_confined_to_approved_modules() -> None:
    imports = {
        path.relative_to(_SOURCE_ROOT).as_posix() for path in _SOURCE_ROOT.rglob("*.py") if _imports_raw_client(path)
    }

    unexpected = imports - _ALLOWED_RAW_CLIENT_IMPORTS
    assert not unexpected, f"Use ClickHouseExecutor instead of the raw client in: {sorted(unexpected)}"


def _imports_raw_client(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _RAW_CLIENT_MODULE:
            return True
        if isinstance(node, ast.Import) and any(alias.name == _RAW_CLIENT_MODULE for alias in node.names):
            return True
    return False
