# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import shlex
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

# TODO: Replace this blunt local-run suppression with a cleaner NAT/local invoke
# output mode once the POC behavior is stable.
warnings.filterwarnings("ignore")

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends.filesystem import FilesystemBackend  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from nemo_cli_agent.utils import print_loaded_skills  # noqa: E402

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_MD = AGENT_ROOT / "AGENTS.md"
DEEP_AGENTS_MD = AGENT_ROOT / "DEEP_AGENTS.md"
SKILLS_DIR = AGENT_ROOT / ".agents" / "skills"

VERBOSE_ENV_VAR = "NEMO_CLI_AGENT_VERBOSE"

os.environ.setdefault("NAT_TELEMETRY_ENABLED", "false")

_NEMO_BIN: str | None = shutil.which("nemo") or (str(p) if (p := Path(sys.prefix) / "bin" / "nemo").exists() else None)


def _load_prompt_file(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("%s not found; using fallback prompt fragment", path.name)
        return fallback


def _load_system_prompt() -> str:
    base_prompt = _load_prompt_file(
        AGENTS_MD,
        "You are a NeMo Platform CLI assistant. Print the nemo commands you run, then execute them.",
    )
    deepagents_prompt = _load_prompt_file(
        DEEP_AGENTS_MD,
        "Use the available skills first. Use nemo_cli only for single nemo commands.",
    )
    return f"{base_prompt.rstrip()}\n\n{deepagents_prompt.strip()}"


def _run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
    if result.returncode == 0:
        return result.stdout or "(no output)"
    return f"Error (exit code {result.returncode}): {result.stderr or result.stdout}"


@tool
def nemo_cli(command: str) -> str:
    """Run one `nemo ...` CLI command and return the output.

    The command must be one `nemo ...` invocation. Shell syntax is not
    supported.

    Args:
        command: The full CLI command to run, for example `nemo workspaces list`
            or `nemo skills install --agent generic`.

    Returns:
        The printed command and its stdout, or an error message if it fails.
    """
    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"Error: invalid command syntax: {e}"
    if not args or Path(args[0]).name != "nemo":
        return "Error: only 'nemo' commands are allowed."
    resolved = _NEMO_BIN or shutil.which(args[0])
    if resolved is None:
        venv_path = Path(sys.prefix) / "bin" / args[0]
        if venv_path.exists():
            resolved = str(venv_path)
        else:
            return f"Error: '{args[0]}' not found on PATH or in venv ({sys.prefix}/bin/)"
    args[0] = resolved

    # Generic skill installs are project-scoped. Pin the project root to this
    # example folder so the installer writes to `<AGENT_ROOT>/.agents/skills/`
    # regardless of where the user invoked the agent from.
    is_generic_skill_install = (
        args[1:4] == ["skills", "install", "--agent"] and "generic" in args[4:] and "--project-root" not in args
    )
    if is_generic_skill_install:
        args.extend(["--project-root", str(AGENT_ROOT)])

    try:
        return _run_command(args, timeout=120 if is_generic_skill_install else 60)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def _get_model():
    """Get the LLM from NAT's builder context (YAML llms: section)."""
    from nat.builder.framework_enum import LLMFrameworkEnum
    from nat.builder.sync_builder import SyncBuilder

    return SyncBuilder.current().get_llm("agent", wrapper_type=LLMFrameworkEnum.LANGCHAIN)


def _has_installed_skills() -> bool:
    """Return True if ``SKILLS_DIR`` already contains at least one skill entry."""
    return SKILLS_DIR.is_dir() and any(SKILLS_DIR.iterdir())


def _ensure_skills_installed() -> None:
    """Install the NeMo CLI skills into the agent folder on first run.

    No-op once ``.agents/skills/`` is populated. Failures are reported but
    don't block the agent from starting — the agent can always re-run the
    install through its ``nemo_cli`` tool.
    """
    if _has_installed_skills():
        return
    nemo_bin = _NEMO_BIN or shutil.which("nemo")
    if nemo_bin is None:
        print(
            f"Skipping initial skill install: 'nemo' not found on PATH or in {sys.prefix}/bin/",
            flush=True,
        )
        return
    print(f"Installing NeMo CLI skills into {SKILLS_DIR} (first run)...", flush=True)
    try:
        result = subprocess.run(
            [nemo_bin, "skills", "install", "--agent", "generic", "--project-root", str(AGENT_ROOT)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        print(f"Initial skill install failed: {type(exc).__name__}: {exc}", flush=True)
        return
    if result.returncode == 0:
        print("Skills installed.", flush=True)
    else:
        print(
            f"Initial skill install failed (exit {result.returncode}): {(result.stderr or result.stdout).strip()}",
            flush=True,
        )


def create_nemo_cli_agent(config=None):
    """Create the NeMo Platform CLI Deep Agent.

    Wires the DeepAgents ``SkillsMiddleware`` against a real filesystem
    backend rooted at this example folder so the agent can see the
    ``.agents/skills/`` directory we populate via ``nemo skills install``.
    The middleware injects every ``SKILL.md``'s name + description into
    the system prompt; the agent then reads the full skill file via the
    built-in ``read_file`` tool when one matches the user's request.

    TODO: For cloud-bundled deployments where the agent has no writeable
    filesystem, swap ``FilesystemBackend`` for a read-only backend that
    wraps an in-memory ``{path: bytes}`` map loaded from the wheel at
    import time. The ``SkillsMiddleware`` only consumes the backend's
    ``ls`` and ``download_files`` APIs, so a tiny custom backend is
    enough — we don't need ``StateBackend`` plumbing through every
    ``invoke()``.
    """
    _ensure_skills_installed()
    model = _get_model()
    # ``virtual_mode=False`` is the historical default and matches our
    # assumption that ``SKILLS_DIR`` is referenced via its absolute path.
    # Spelling it out silences the ``virtual_mode default will change in
    # deepagents==0.6.0`` deprecation warning.
    backend = FilesystemBackend(root_dir=AGENT_ROOT, virtual_mode=False)
    # Verbose mode prints the loaded-skill catalog and the post-middleware
    # system prompt. Lazy-import the verbose middleware so the default
    # (non-verbose) path never pulls in ``langchain.agents.middleware.types``
    # — that import chain transitively loads ``langgraph`` and triggers a
    # ``LangChainPendingDeprecationWarning`` before any warning filter we
    # set can run.
    extra_middleware: list = []
    if os.environ.get(VERBOSE_ENV_VAR) == "1":
        print_loaded_skills(SKILLS_DIR)
        from nemo_cli_agent.verbose import SystemPromptDumpMiddleware

        extra_middleware.append(SystemPromptDumpMiddleware())
    return create_deep_agent(
        model=model,
        tools=[nemo_cli],
        system_prompt=_load_system_prompt(),
        backend=backend,
        skills=[str(SKILLS_DIR)],
        middleware=extra_middleware,
    )


# Module-level graph factory used by ``nat_compatible_langgraph_wrapper`` in
# ``nemo-cli-agent.yml``. The ``agent`` alias is kept for ad-hoc debugging with
# other graph-loading paths.
agent = create_nemo_cli_agent
