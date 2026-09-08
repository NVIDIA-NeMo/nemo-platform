# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Low-level subprocess spawning shared by provider-specific durability strategies."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any


def spawn_detached_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    log: IO[Any],
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[Any]:
    """Start one new-session child; callers retain identity and resume policy."""
    return subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=None if env is None else dict(env),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
