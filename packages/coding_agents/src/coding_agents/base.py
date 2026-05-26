from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from coding_agents.events import ResultEvent
from coding_agents.permissions import PermissionPolicy


@dataclass(frozen=True)
class AgentAvailability:
    installed: bool
    authenticated: bool
    version: str | None = None
    detail: str | None = None


class CodingAgent(ABC):
    """A headless coding-agent backend (Claude Code, Codex, ...).

    YOLO mode: one prompt in, one ResultEvent out. No multi-turn state,
    no live event stream. If a caller needs progress reporting or
    multi-turn conversation, that lives in a higher layer.
    """

    name: ClassVar[str]

    @abstractmethod
    async def check_available(self) -> AgentAvailability:
        """Verify the CLI is installed and the user is authenticated.

        Raises AgentNotInstalledError or NotAuthenticatedError if not.
        Returns availability metadata otherwise.
        """

    @abstractmethod
    async def run(
        self,
        prompt: str,
        *,
        working_dir: Path,
        timeout: float | None = None,
        permissions: PermissionPolicy | None = None,
        system_prompt: str | None = None,
        append_system_prompt: str | None = None,
        max_budget_usd: float | None = None,
        model: str | None = None,
        extra_env: Mapping[str, str] | None = None,
        extra_cli_args: Sequence[str] | None = None,
        resume_session_id: str | None = None,
    ) -> ResultEvent:
        """Run one coding-agent invocation. Blocks until the agent completes.

        Pass `resume_session_id=prev_result.session_id` to continue a prior
        conversation; the agent picks up where it left off.

        Raises:
            AgentRunError: process couldn't produce a result event.
            TimeoutError: `timeout` expired before completion.
            PermissionModeUnsafeError: `permissions.mode` is not headless-safe.
        """
