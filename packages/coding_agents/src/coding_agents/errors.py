class CodingAgentError(Exception):
    """Base for all errors raised by coding_agents."""


class AgentNotInstalledError(CodingAgentError):
    """Raised when the agent CLI is not installed or not on PATH."""


class NotAuthenticatedError(CodingAgentError):
    """Raised when the agent CLI is installed but the user is not logged in."""


class PermissionModeUnsafeError(CodingAgentError):
    """Raised when a run is configured with a permission mode that would
    hang in headless mode (because it waits for an interactive prompt)."""


class AgentRunError(CodingAgentError):
    """Raised when the agent process couldn't produce a result event
    (crashed, killed, never started, or malformed output)."""
