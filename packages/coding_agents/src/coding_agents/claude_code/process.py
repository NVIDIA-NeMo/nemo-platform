# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from collections.abc import Mapping

_DROP_EXACT = frozenset({"CLAUDECODE", "CLAUDE_EFFORT"})
_DROP_PREFIXES = ("CLAUDE_CODE_",)


def scrubbed_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a child-process env that doesn't signal 'you are inside Claude Code'.

    Strips variables that would cause a child `claude` invocation to detect a
    parent session, reuse its config dir, or get confused about working dir.
    Keeps everything else (PATH, HOME, ANTHROPIC_*, etc.).

    Why: the library is intended to be called from automated workflows that
    may themselves be running inside Claude Code (or another agent). Without
    scrubbing, the child can pick up the parent's session ID via env and
    write to the wrong place.
    """
    env = {
        k: v for k, v in os.environ.items() if k not in _DROP_EXACT and not any(k.startswith(p) for p in _DROP_PREFIXES)
    }
    if extra:
        env.update(extra)
    return env
