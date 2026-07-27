# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# TODO(shared-module): exact copy of experimentalist components/repository.py (clone helpers for backend); unify into a shared package.

"""Fetch an agent from a git repo and publish a candidate as a draft PR/MR.

Fetching clones ``<git-url>[@<ref>]`` into a local checkout (retaining ``.git`` so
it can serve as a push target). Publishing takes that checkout plus a directory of
updated agent files, creates a branch off the source ref, commits the files, pushes,
and opens a draft pull request (GitHub) or merge request (GitLab) via the ``gh`` /
``glab`` CLIs. Branching from the exact source ref keeps the published change
reproducible against the commit the agent came from.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Upper bound (seconds) for any single git/gh/glab call during publishing, so a
# network stall or auth prompt can't hang the optimizer's awaited publish path.
_COMMAND_TIMEOUT = 120

# Matches the ``userinfo@`` of a URL (e.g. ``https://oauth2:<token>@host``). Git clone URLs
# can embed credentials there, so we strip them before logging a URL.
_CREDENTIAL_RE = re.compile(r"://[^/@]+@")

_AGENT_PATH_ERROR = "agent path must be a normalized relative POSIX path"
_AGENT_PATH_CHECKOUT_ERROR = "agent path must stay within the checkout without symlinks"


def _redact_url(url: str) -> str:
    """Return *url* with any embedded ``userinfo@`` credentials masked, safe for logging."""
    return _CREDENTIAL_RE.sub("://***@", url)


def _validated_agent_path(agent_path: str) -> str:
    """Return a safe relative POSIX agent path or raise a controlled error."""
    agent_path = agent_path.removesuffix("/").removeprefix("./")
    if agent_path == ".":
        return agent_path
    components = agent_path.split("/")
    if (
        not agent_path
        or agent_path.startswith(("/", ":"))
        or "\\" in agent_path
        or any(ord(char) < 32 or ord(char) == 127 for char in agent_path)
        or any(component in {"", ".", ".."} for component in components)
        or any(component.casefold() == ".git" for component in components)
    ):
        raise ValueError(_AGENT_PATH_ERROR)
    return agent_path


def pr_cli_for_repo_url(url: str) -> tuple[str, str] | None:
    """Return the PR CLI and hostname for a supported git remote.

    Substring match on the host family so both github.com and self-hosted
    GitLab (e.g. gitlab.example.com) are recognized.
    """
    if "github" in url:
        cli = "gh"
    elif "gitlab" in url:
        cli = "glab"
    else:
        return None
    hostname = urlsplit(url).hostname if "://" in url else url.partition("@")[2].partition(":")[0]
    return cli, hostname or ""


def split_agent_spec(spec: str) -> tuple[str, str]:
    """Split an agent spec ``<url@ref>#<agent_path>`` into ``(core_spec, agent_path)``.

    The ``#<agent_path>`` fragment carries the agent's location within the repo (monorepo
    support), so repo, rev, and sub-path all travel together on the one ``--agent`` value.
    A spec with no fragment has agent_path ``"."`` (whole-repo agent).
    """
    core, separator, fragment = spec.partition("#")
    agent_path = fragment if separator else "."
    return core, _validated_agent_path(agent_path)


# Glob patterns for files never copied into the published branch: generated/run-local
# files, VCS/tool dirs, and build artifacts. Matched with fnmatch against each name.
_EXCLUDE_GLOBS = (
    "metadata.json",
    "harbor_wrapper.py",
    "dind_environment.py",
    "architecture.md",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
)


class AgentSource(BaseModel):
    """Git provenance of the agent under test.

    Set when ``--agent`` is given as ``<git-url>@<ref>[#<agent_path>]``. ``repo_url`` is the
    clone URL (the PR/MR target remote), ``ref`` is the base branch/tag/commit the agent was
    checked out from, and ``agent_path`` is the agent's location within the repo (``"."`` for
    a whole-repo agent) — the subtree that archival/PR overlays and commits.
    """

    repo_url: str
    ref: str
    agent_path: str = "."


class AgentCloneError(ValueError):
    """A git source could not be materialized."""


def split_git_ref(spec: str) -> tuple[str, str | None]:
    """Split a ``<git-url>.git@<ref>`` spec into ``(url, ref)``.

    Locates the first ``.git@`` marker in the repository path, excluding URL
    authority/userinfo. A spec without a path marker has no ref.
    """
    marker = ".git@"
    if "://" in spec:
        try:
            parsed = urlsplit(spec)
        except (ValueError, UnicodeError):
            return spec, None
        idx = parsed.path.find(marker)
        if idx == -1:
            return spec, None
        repo_path = parsed.path[: idx + len(".git")]
        ref = parsed.path[idx + len(marker) :]
        return parsed._replace(path=repo_path).geturl(), ref

    user_end = spec.find("@")
    path_start = spec.find(":", user_end + 1) if user_end >= 0 else -1
    search_start = path_start + 1 if path_start >= 0 else 0
    idx = spec.find(marker, search_start)
    if idx == -1:
        return spec, None
    return spec[: idx + len(".git")], spec[idx + len(marker) :]


def looks_like_git(spec: str) -> bool:
    """Return True if *spec* looks like a git URL (vs a local path)."""
    url, _ = split_git_ref(spec)
    return "://" in url or url.startswith("git@") or url.endswith(".git")


def clone_agent_repo(spec: str, dest: Path, *, clone_depth: int | None = None) -> AgentSource:
    """Clone ``<git-url>[@<ref>][#<agent_path>]`` into *dest* (retaining ``.git``) and return provenance.

    The clone keeps ``.git``/``origin`` so *dest* can serve as the PR/MR push target. The whole
    repo is cloned; ``agent_path`` (the ``#`` fragment, ``"."`` when omitted) records the agent's
    sub-path within it for downstream overlay/commit. When no ``@ref`` is given, the checked-out
    default branch is resolved and recorded. When ``clone_depth`` is given a shallow clone is made
    (it must be deep enough to branch from ``ref``). Raises on git failure (callers decide how to
    handle).
    """
    core, agent_path = split_agent_spec(spec)
    url, ref = split_git_ref(core)
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    safe_url = _redact_url(url)
    logger.info(f"[AGENT] cloning {safe_url} -> {dest}")
    clone_cmd = ["git", "clone", "--quiet"]
    if clone_depth is not None:
        clone_cmd += ["--depth", str(clone_depth)]
    clone_cmd += [url, str(dest)]

    def run_git(command: list[str], operation: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(  # noqa: S603, S607
                command,
                capture_output=True,
                text=True,
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=_COMMAND_TIMEOUT,
            )
        except subprocess.CalledProcessError as exc:
            details = _redact_url((exc.stderr or exc.stdout or "").strip())
            suffix = f": {details}" if details else ""
            raise AgentCloneError(f"{operation} failed for {safe_url} (exit status {exc.returncode}){suffix}") from None
        except subprocess.TimeoutExpired:
            raise AgentCloneError(f"{operation} timed out after {_COMMAND_TIMEOUT}s for {safe_url}") from None
        except OSError as exc:
            raise AgentCloneError(f"could not run 'git' during {operation} for {safe_url}: {exc}") from None

    run_git(clone_cmd, "git clone")
    if ref:
        run_git(["git", "-C", str(dest), "checkout", "--quiet", ref], "git checkout")
    else:
        ref = run_git(
            ["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
            "git rev-parse",
        ).stdout.strip()
    # repo_url is provenance (it becomes the candidate's source_link), so keep it
    # credential-free; the conventional ssh ``git`` user is not a secret.
    repo_url = url if url.startswith("ssh://git@") or "://" not in url else _redact_url(url)
    return AgentSource(repo_url=repo_url, ref=ref, agent_path=agent_path)


class PRPublisherError(RuntimeError):
    """Raised when publishing the winner PR/MR fails."""


class PRPublisher:
    """Open a draft PR/MR for the winning candidate against the agent's source repo.

    Args:
        agent_dir: The local git checkout of the agent under test (its ``origin``
            remote is the PR/MR target). Must be a git work tree.
    """

    def __init__(self, *, agent_dir: Path) -> None:
        self.agent_dir = Path(agent_dir).resolve()

    def _run(self, cmd: list[str], *, cwd: Path | None = None) -> str:
        """Run a command and return stdout; raise :class:`PRPublisherError` on failure.

        Bounded by ``_COMMAND_TIMEOUT`` so a git/gh/glab call that blocks on the
        network or an auth prompt can never hang the awaited publish path.
        """
        command = _redact_url(" ".join(cmd))
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(cwd or self.agent_dir),
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT,
                stdin=subprocess.DEVNULL,  # never block on an interactive auth prompt
            )
        except subprocess.TimeoutExpired:
            raise PRPublisherError(f"command timed out after {_COMMAND_TIMEOUT}s: {command}") from None
        except OSError as exc:  # e.g. git/gh/glab not installed -> FileNotFoundError
            raise PRPublisherError(f"could not run {cmd[0]!r}: {exc}") from None
        if result.returncode != 0:
            stderr = _redact_url(result.stderr.strip())
            raise PRPublisherError(f"command failed ({result.returncode}): {command}\n{stderr}")
        return result.stdout.strip()

    # -- helpers --------------------------------------------------------------

    def _origin_url(self) -> str:
        return self._run(["git", "remote", "get-url", "origin"])

    def _is_remote_branch(self, ref: str) -> bool:
        """Return True if *ref* is a branch on origin (vs a tag or bare commit)."""
        return bool(self._run(["git", "ls-remote", "--heads", "origin", ref]))

    def _default_branch(self) -> str:
        """Resolve origin's default branch (e.g. ``main``) from its local symbolic HEAD.

        Reads ``refs/remotes/origin/HEAD``, which the fresh clone in
        ``clone_agent_repo`` sets, so no extra network round-trip is needed. Strips
        only the ``origin/`` prefix so slashed branch names (e.g. ``release/2026.07``)
        survive intact.
        """
        ref = self._run(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"])  # e.g. "origin/main"
        prefix = "origin/"
        if not ref.startswith(prefix) or ref == "origin/HEAD":
            raise PRPublisherError(f"could not resolve origin default branch (got {ref!r})")
        return ref[len(prefix) :]

    @staticmethod
    def _overlay(winner_dir: Path, dest: Path) -> None:
        """Copy the winner's agent files over *dest*, excluding files matching ``_EXCLUDE_GLOBS``.

        Exclusions apply at the top level and recursively (via ``shutil.ignore_patterns``),
        so nested ``__pycache__``/``*.pyc`` and the like never reach the published branch.
        """
        dest.mkdir(parents=True, exist_ok=True)
        ignore = shutil.ignore_patterns(*_EXCLUDE_GLOBS)
        for item in winner_dir.iterdir():
            if any(fnmatch(item.name, pat) for pat in _EXCLUDE_GLOBS):
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True, ignore=ignore)
            else:
                shutil.copy2(item, target)

    def _validated_subtree(self, agent_path: str) -> Path:
        """Resolve an agent subtree without following a path component symlink."""
        agent_path = _validated_agent_path(agent_path)
        if agent_path == ".":
            return self.agent_dir
        subtree = self.agent_dir
        try:
            for component in agent_path.split("/"):
                subtree /= component
                if subtree.is_symlink():
                    raise ValueError(_AGENT_PATH_CHECKOUT_ERROR)
            if not subtree.resolve(strict=False).is_relative_to(self.agent_dir):
                raise ValueError(_AGENT_PATH_CHECKOUT_ERROR)
        except OSError:
            raise ValueError(_AGENT_PATH_CHECKOUT_ERROR) from None
        return subtree

    def _snapshot_subtree(self, src_dir: Path, agent_path: str) -> None:
        """Replace the ``agent_path`` subtree with *src_dir*'s files (deletions captured).

        ``git rm`` the existing subtree first so files the candidate removed don't linger,
        using literal pathspec semantics, then overlay the candidate's files. ``agent_path``
        ``"."`` targets the whole repo.
        """
        self._validated_subtree(agent_path)
        self._run(["git", "--literal-pathspecs", "rm", "-r", "-q", "-f", "--ignore-unmatch", "--", agent_path])
        subtree = self._validated_subtree(agent_path)
        stale_items = (
            (item for item in subtree.iterdir() if item.name.casefold() != ".git") if agent_path == "." else (subtree,)
        )
        for item in stale_items:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
        self._overlay(Path(src_dir), subtree)
        self._run(["git", "--literal-pathspecs", "add", "-A", "--", agent_path])

    # -- public API -----------------------------------------------------------

    def push_branch(
        self,
        *,
        src_dir: Path,
        branch: str,
        base_ref: str,
        message: str,
        agent_path: str = ".",
    ) -> bool:
        """Archive one candidate: push *src_dir* as *branch* cut from *base_ref*.

        Snapshots the ``agent_path`` subtree (``git rm`` + overlay, capturing deletions).
        Skip-if-exists and idempotent without force-pushing: returns ``False`` when *branch*
        already exists on origin or the result is byte-identical to *base_ref* (empty diff),
        ``True`` when a new branch was pushed. Used to archive every candidate to its own
        branch during a run.
        """
        agent_path = _validated_agent_path(agent_path)
        if self._is_remote_branch(branch):
            logger.info(f"[PUSH] branch {branch} already exists on origin; skipping")
            return False
        self._run(["git", "fetch", "origin", base_ref])
        self._run(["git", "checkout", "-B", branch, "FETCH_HEAD"])
        self._snapshot_subtree(Path(src_dir), agent_path)
        if not self._run(["git", "--literal-pathspecs", "status", "--porcelain", "--", agent_path]):
            logger.info(f"[PUSH] {branch} identical to {base_ref}; skipping")
            return False
        self._run(["git", "--literal-pathspecs", "commit", "--only", "-m", message, "--", agent_path])
        self._run(["git", "push", "-u", "origin", branch])
        return True

    def publish(
        self,
        *,
        winner_dir: Path,
        branch: str,
        base_ref: str,
        title: str,
        body: str,
        draft: bool = True,
        agent_path: str = ".",
        base_branch_override: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """Create a branch with the winner's code and open a draft PR/MR.

        Args:
            winner_dir: Directory holding the winning candidate's agent files.
            branch: Name of the branch to create and push.
            base_ref: Source ref the branch is created from. Used as the PR/MR base
                when it is a branch; for a tag/commit source the base falls back to
                the remote's default branch (a PR/MR base must be a branch).
            title: PR/MR title.
            body: PR/MR description.
            draft: Open as a draft (default True).
            agent_path: In-repo sub-path the winner's files overlay (``"."`` = whole repo).
            base_branch_override: Explicit PR/MR base branch; overrides the ``base_ref``/default.
            labels: Optional labels applied to the PR/MR.

        Returns:
            The created PR/MR URL.
        """
        agent_path = _validated_agent_path(agent_path)
        origin = self._origin_url()
        target = pr_cli_for_repo_url(origin)
        if target is None:
            raise PRPublisherError(f"unsupported remote host for PR creation: {_redact_url(origin)}")
        cli, _ = target

        # Branch from the exact source ref (branch, tag, or commit) via FETCH_HEAD so
        # the change is reproducible against the commit the agent came from.
        self._run(["git", "fetch", "origin", base_ref])
        self._run(["git", "checkout", "-B", branch, "FETCH_HEAD"])
        self._snapshot_subtree(Path(winner_dir), agent_path)
        # Nothing to commit → no PR (winner identical to base).
        status = self._run(["git", "--literal-pathspecs", "status", "--porcelain", "--", agent_path])
        if not status:
            logger.info("[TERMINATOR] winner is identical to base ref; skipping PR creation")
            return ""
        self._run(["git", "--literal-pathspecs", "commit", "--only", "-m", title, "--", agent_path])
        self._run(["git", "push", "--force-with-lease", "-u", "origin", branch])

        # A PR/MR base must be a branch: an explicit override wins; else target base_ref when it
        # is a branch, else the remote's default branch (the source may be a tag/commit).
        pr_base = base_branch_override or (base_ref if self._is_remote_branch(base_ref) else self._default_branch())
        if cli == "gh":
            cmd = ["gh", "pr", "create", "--base", pr_base, "--head", branch, "--title", title, "--body", body]
            if draft:
                cmd.append("--draft")
            for label in labels or []:
                cmd += ["--label", label]
            return self._run(cmd)
        # gitlab
        cmd = ["glab", "mr", "create", "--source-branch", branch, "--target-branch", pr_base]
        cmd += ["--title", title, "--description", body, "--yes"]
        if draft:
            cmd.append("--draft")
        if labels:
            cmd += ["--label", ",".join(labels)]
        return self._run(cmd)
