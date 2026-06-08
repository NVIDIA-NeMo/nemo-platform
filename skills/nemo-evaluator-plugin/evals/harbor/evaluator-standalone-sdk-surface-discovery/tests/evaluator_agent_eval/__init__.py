"""Shared Evaluator agent-eval verifier helpers staged with ACES tasks."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_sdk_path() -> None:
    for root in _repo_root_candidates():
        sdk_src = root / "packages" / "nemo_evaluator_sdk" / "src"
        if sdk_src.exists():
            sys.path.insert(0, str(sdk_src))
            os.environ["PYTHONPATH"] = f"{sdk_src}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"
            return


def _repo_root_candidates() -> list[Path]:
    return [
        Path("/workspace/repo"),
        Path("/workspace"),
        Path("/app"),
        Path.cwd(),
        *Path(__file__).resolve().parents,
    ]


_ensure_sdk_path()
