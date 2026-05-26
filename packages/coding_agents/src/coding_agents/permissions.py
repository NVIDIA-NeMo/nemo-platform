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
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    def is_headless_safe(self) -> bool:
        return self.mode in _HEADLESS_SAFE_MODES
