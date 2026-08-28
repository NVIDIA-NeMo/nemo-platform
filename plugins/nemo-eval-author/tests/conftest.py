# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load walkthrough env defaults before sandbox tests import prepare_sandbox."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / "walkthrough" / "env"


def _load_env_file(path: Path) -> None:
    result = subprocess.run(
        ["bash", "-c", f"set -a; source '{path}'; env -0"],
        capture_output=True,
        check=True,
    )
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        key, _, value = entry.partition(b"=")
        os.environ[key.decode()] = value.decode()


_load_env_file(_ENV_FILE)
