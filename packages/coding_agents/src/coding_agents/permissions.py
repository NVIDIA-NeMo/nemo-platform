# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from enum import StrEnum


class PermissionMode(StrEnum):
    """Mirrors Claude Code's --permission-mode values, plus BYPASS as an
    alias for --dangerously-skip-permissions.

    Modes safe in headless: BYPASS, PLAN. The others wait for an
    interactive prompt that never arrives.
    """

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    BYPASS = "bypassPermissions"
    PLAN = "plan"


_HEADLESS_SAFE_MODES = frozenset({PermissionMode.BYPASS, PermissionMode.PLAN})


@dataclass(frozen=True)
class PermissionPolicy:
    mode: PermissionMode = PermissionMode.BYPASS
    # Tuples (not lists) so the frozen contract actually holds — callers
    # can't do policy.allowed_tools.append(...) to sneak around immutability.
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    disallowed_tools: tuple[str, ...] = field(default_factory=tuple)

    def is_headless_safe(self) -> bool:
        return self.mode in _HEADLESS_SAFE_MODES
