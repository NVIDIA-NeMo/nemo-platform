# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for git-source resolution and PR/MR publishing.

No network or real git: the git-ref parsing helpers are pure, and PRPublisher's
single command boundary (``_run``) is stubbed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.experimentalist.components import repository as repo
from nemo_experimentalist_plugin.experimentalist.components.repository import (
    AgentCloneError,
    AgentSource,
    PRPublisher,
    PRPublisherError,
    clone_agent_repo,
    looks_like_git,
    split_agent_spec,
    split_git_ref,
)

# ---------------------------------------------------------------------------
# git-ref parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "url", "ref"),
    [
        (
            "ssh://git@gitlab.example.com:12051/org/agents-under-test.git@main",
            "ssh://git@gitlab.example.com:12051/org/agents-under-test.git",
            "main",
        ),
        # No ref: the git@ user in the ssh URL must NOT be treated as a ref.
        (
            "ssh://git@gitlab.example.com:12051/org/agents-under-test.git",
            "ssh://git@gitlab.example.com:12051/org/agents-under-test.git",
            None,
        ),
        ("git@github.com:org/repo.git", "git@github.com:org/repo.git", None),
        ("git@github.com:org/repo.git@feature/x", "git@github.com:org/repo.git", "feature/x"),
        ("https://github.com/org/repo.git@v1.2", "https://github.com/org/repo.git", "v1.2"),
        (
            "https://token.git@github.com/org/repo.git",
            "https://token.git@github.com/org/repo.git",
            None,
        ),
        (
            "https://token.git@github.com/org/repo.git@main",
            "https://token.git@github.com/org/repo.git",
            "main",
        ),
        ("token.git@github.com:org/repo.git", "token.git@github.com:org/repo.git", None),
        ("token.git@github.com:org/repo.git@main", "token.git@github.com:org/repo.git", "main"),
        (
            "https://token.git@github.com/org/repo.git@feature/x.git@debug?access_token=secret",
            "https://token.git@github.com/org/repo.git?access_token=secret",
            "feature/x.git@debug",
        ),
        ("../repo.git@feature/x", "../repo.git", "feature/x"),
    ],
)
def test_split_git_ref(spec: str, url: str, ref: str | None) -> None:
    assert split_git_ref(spec) == (url, ref)


def test_looks_like_git() -> None:
    assert looks_like_git("ssh://git@host:1/grp/repo.git@main")
    assert looks_like_git("git@github.com:org/repo.git")
    assert looks_like_git("https://github.com/org/repo.git")
    assert not looks_like_git("examples/terminal-bench-agent")
    assert not looks_like_git("/abs/local/dir")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/org/repo.git", ("gh", "github.com")),
        ("ssh://git@github.com/org/repo.git", ("gh", "github.com")),
        ("git@github.com:org/repo.git", ("gh", "github.com")),
        ("https://gitlab.com/org/repo.git", ("glab", "gitlab.com")),
        (
            "ssh://git@gitlab-master.example.com:12051/org/repo.git",
            ("glab", "gitlab-master.example.com"),
        ),
        ("git@gitlab-master.example.com:org/repo.git", ("glab", "gitlab-master.example.com")),
        # Self-hosted GitLab under any hostname is recognized by the host family.
        ("https://gitlab.example.com/org/repo.git", ("glab", "gitlab.example.com")),
        (
            "https://oauth2:secret@gitlab-master.example.com/org/repo.git",  # trufflehog:ignore
            ("glab", "gitlab-master.example.com"),
        ),
        ("https://bitbucket.org/org/repo.git", None),
        ("not a repository URL", None),
    ],
)
def test_pr_cli_for_repo_url(url: str, expected: tuple[str, str] | None) -> None:
    assert repo.pr_cli_for_repo_url(url) == expected


def test_redact_url_masks_userinfo() -> None:
    assert (
        repo._redact_url("https://oauth2:secret-token@gitlab.example.com/g/r.git")  # trufflehog:ignore
        == "https://***@gitlab.example.com/g/r.git"
    )
    assert repo._redact_url("https://github.com/org/repo.git") == "https://github.com/org/repo.git"


# ---------------------------------------------------------------------------
# PRPublisher (stubbed command boundary)
# ---------------------------------------------------------------------------


class _StubPublisher(PRPublisher):
    """PRPublisher that records commands and returns canned outputs instead of shelling out."""

    def __init__(
        self,
        *,
        agent_dir: Path,
        origin: str,
        status: str,
        branches: tuple[str, ...] = ("main",),
        default_branch: str = "main",
    ) -> None:
        super().__init__(agent_dir=agent_dir)
        self.calls: list[list[str]] = []
        self._origin = origin
        self._status = status
        self._branches = branches  # refs that ls-remote --heads reports as branches
        self._default_head = default_branch  # origin/HEAD target

    def _run(self, cmd: list[str], *, cwd: Path | None = None) -> str:
        self.calls.append(cmd)
        if cmd[:3] == ["git", "remote", "get-url"]:
            return self._origin
        if cmd[:2] == ["git", "ls-remote"] and "--heads" in cmd:
            ref = cmd[-1]
            return f"deadbeef\trefs/heads/{ref}" if ref in self._branches else ""
        if cmd[:2] == ["git", "rev-parse"] and cmd[-1] == "origin/HEAD":
            return f"origin/{self._default_head}"
        if cmd[:3] == ["git", "--literal-pathspecs", "status"]:
            return self._status
        if cmd[:1] == ["glab"]:
            return "https://gitlab.example.com/org/agents-under-test/-/merge_requests/1"
        if cmd[:1] == ["gh"]:
            return "https://github.com/org/repo/pull/1"
        return ""


def _winner(tmp_path: Path) -> Path:
    w = tmp_path / "winner"
    w.mkdir()
    (w / "main.py").write_text("print('improved')\n")
    (w / "metadata.json").write_text("{}")  # must be skipped
    return w


def _git(checkout: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def test_publish_gitlab_opens_draft_mr(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="ssh://git@gitlab.example.com:12051/org/agents-under-test.git",
        status=" M main.py",
    )
    url = pub.publish(
        winner_dir=_winner(tmp_path),
        branch="optimizer/run-1-agent-2",
        base_ref="main",
        title="Experimentalist: candidate agent-2",
        body="summary",
    )
    assert url.endswith("/merge_requests/1")
    glab = next(c for c in pub.calls if c[0] == "glab")
    assert "mr" in glab and "create" in glab and "--draft" in glab
    assert "--source-branch" in glab and "optimizer/run-1-agent-2" in glab
    assert "--target-branch" in glab and "main" in glab
    assert ["git", "fetch", "origin", "main"] in pub.calls
    assert ["git", "push", "--force-with-lease", "-u", "origin", "optimizer/run-1-agent-2"] in pub.calls
    assert ["git", "ls-remote", "--heads", "origin", "main"] in pub.calls
    # Generated file was not committed (overlay skipped it).
    assert not (agent_dir / "metadata.json").exists()
    assert (agent_dir / "main.py").read_text() == "print('improved')\n"


def test_publish_github_opens_draft_pr(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="https://github.com/org/repo.git",
        status=" M main.py",
    )
    url = pub.publish(
        winner_dir=_winner(tmp_path),
        branch="optimizer/x",
        base_ref="main",
        title="t",
        body="b",
    )
    assert url.endswith("/pull/1")
    gh = next(c for c in pub.calls if c[0] == "gh")
    assert gh[:3] == ["gh", "pr", "create"] and "--draft" in gh


def test_publish_skips_build_artifacts(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    # Winner dir with top-level and NESTED build artifacts that must not be committed.
    winner = tmp_path / "winner"
    (winner / "pkg" / "__pycache__").mkdir(parents=True)
    (winner / "main.py").write_text("print('improved')\n")
    (winner / "stray.pyc").write_bytes(b"\x00")
    (winner / "__pycache__").mkdir()
    (winner / "__pycache__" / "main.cpython-313.pyc").write_bytes(b"\x00")
    (winner / "pkg" / "mod.py").write_text("x = 1\n")
    (winner / "pkg" / "__pycache__" / "mod.cpython-313.pyc").write_bytes(b"\x00")

    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="https://github.com/org/repo.git",
        status=" M main.py",
    )
    pub.publish(winner_dir=winner, branch="b", base_ref="main", title="t", body="b")

    # Real source copied; build artifacts (top-level + nested) excluded.
    assert (agent_dir / "main.py").exists()
    assert (agent_dir / "pkg" / "mod.py").exists()
    assert not (agent_dir / "__pycache__").exists()
    assert not (agent_dir / "stray.pyc").exists()
    assert not (agent_dir / "pkg" / "__pycache__").exists()


def test_publish_tag_source_targets_default_branch(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    # base_ref is a tag (not a branch on origin); the MR base must fall back to the
    # remote's default branch (main), while the winner branch is still cut from the tag.
    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="ssh://git@gitlab.example.com:12051/org/agents-under-test.git",
        status=" M main.py",
        branches=("main",),
    )
    pub.publish(
        winner_dir=_winner(tmp_path),
        branch="optimizer/run-1-agent-2",
        base_ref="v1.2",  # a tag
        title="t",
        body="b",
    )
    glab = next(c for c in pub.calls if c[0] == "glab")
    assert glab[glab.index("--target-branch") + 1] == "main"
    assert glab[glab.index("--source-branch") + 1] == "optimizer/run-1-agent-2"
    # The winner branch is cut from the exact source ref via FETCH_HEAD.
    assert ["git", "checkout", "-B", "optimizer/run-1-agent-2", "FETCH_HEAD"] in pub.calls


def test_publish_default_branch_keeps_slashes(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    # A slashed default branch (origin/release/2026.07) must survive the origin/ strip,
    # not be truncated to "2026.07".
    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="https://github.com/org/repo.git",
        status=" M main.py",
        branches=("main",),
        default_branch="release/2026.07",
    )
    pub.publish(winner_dir=_winner(tmp_path), branch="b", base_ref="v1.2", title="t", body="b")
    gh = next(c for c in pub.calls if c[0] == "gh")
    assert gh[gh.index("--base") + 1] == "release/2026.07"


def test_publish_no_diff_skips_pr(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    pub = _StubPublisher(
        agent_dir=agent_dir,
        origin="https://github.com/org/repo.git",
        status="",  # winner identical to base → nothing to commit
    )
    url = pub.publish(winner_dir=_winner(tmp_path), branch="b", base_ref="main", title="t", body="b")
    assert url == ""
    assert not any(c[0] in ("gh", "glab") for c in pub.calls)
    assert not any(c[:2] == ["git", "commit"] for c in pub.calls)


def test_run_failure_includes_command_and_redacted_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **_kwargs) -> repo.subprocess.CompletedProcess[str]:
        return repo.subprocess.CompletedProcess(command, 1, stdout="", stderr="fatal: boom\n")

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    publisher = PRPublisher(agent_dir=tmp_path)

    with pytest.raises(PRPublisherError) as exc_info:
        publisher._run(["git", "fetch", "https://oauth2:token-secret@github.com/org/repo.git"])  # trufflehog:ignore

    message = str(exc_info.value)
    assert "command failed (1): git fetch https://***@github.com/org/repo.git" in message
    assert "fatal: boom" in message
    assert "token-secret" not in message


def test_run_timeout_includes_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs) -> repo.subprocess.CompletedProcess[str]:
        raise repo.subprocess.TimeoutExpired(command, repo._COMMAND_TIMEOUT)

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    publisher = PRPublisher(agent_dir=tmp_path)

    with pytest.raises(PRPublisherError, match="command timed out after 120s: git ls-remote"):
        publisher._run(["git", "ls-remote", "--heads", "origin", "main"])


@pytest.mark.parametrize(
    ("origin", "display"),
    [
        ("https://bitbucket.org/x/y.git", "https://bitbucket.org/x/y.git"),
        ("https://oauth2:secret-token@bitbucket.org/x/y.git", "https://***@bitbucket.org/x/y.git"),  # trufflehog:ignore
    ],
)
def test_publish_unsupported_host_uses_sanitized_remote(tmp_path: Path, origin: str, display: str) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    pub = _StubPublisher(agent_dir=agent_dir, origin=origin, status=" M f")

    with pytest.raises(PRPublisherError) as exc_info:
        pub.publish(winner_dir=_winner(tmp_path), branch="b", base_ref="main", title="t", body="b")

    assert str(exc_info.value) == f"unsupported remote host for PR creation: {display}"
    assert "secret-token" not in str(exc_info.value)


def test_agent_source_model() -> None:
    s = AgentSource(repo_url="ssh://git@h/g/r.git", ref="main")
    assert s.repo_url.endswith("r.git") and s.ref == "main"
    assert s.agent_path == "."  # whole-repo agent by default


# ---------------------------------------------------------------------------
# candidate-storage helpers: spec fragment and agent-path validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "core", "agent_path"),
    [
        ("ssh://git@h/g/r.git@main", "ssh://git@h/g/r.git@main", "."),
        ("ssh://git@h/g/r.git@main#pkg/agent", "ssh://git@h/g/r.git@main", "pkg/agent"),
        ("https://h/g/r.git#sub", "https://h/g/r.git", "sub"),
        # Benign fragment forms are normalized rather than rejected.
        ("https://h/g/r.git#pkg/agent/", "https://h/g/r.git", "pkg/agent"),
        ("https://h/g/r.git#./pkg/agent", "https://h/g/r.git", "pkg/agent"),
        ("https://h/g/r.git#./", "https://h/g/r.git", "."),
    ],
)
def test_split_agent_spec(spec: str, core: str, agent_path: str) -> None:
    assert split_agent_spec(spec) == (core, agent_path)


@pytest.mark.parametrize(
    "agent_path",
    [
        ":(top,glob)**",
        ".git",
        ".GIT/hooks",
        "pkg/.GiT/hooks",
        "..",
        "../outside",
        "pkg/../outside",
        "/absolute",
        "pkg\\agent",
        "pkg//agent",
        "pkg/./agent",
        "",
        "pkg/\x00agent",
    ],
)
def test_split_agent_spec_rejects_unsafe_agent_path_without_echo(agent_path: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        split_agent_spec(f"https://github.com/org/repo.git#{agent_path}")

    assert str(exc_info.value) == "agent path must be a normalized relative POSIX path"
    if agent_path:
        assert agent_path not in str(exc_info.value)


@pytest.mark.parametrize("agent_path", [":(top,glob)**", "pkg/.GiT/hooks"])
@pytest.mark.parametrize("boundary", ["snapshot", "push", "publish"])
def test_publisher_rejects_unsafe_agent_path_before_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    agent_path: str,
) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    publisher = _StubPublisher(
        agent_dir=agent_dir,
        origin="https://github.com/org/repo.git",
        status=" M main.py",
    )
    winner = _winner(tmp_path)
    overlay_calls: list[Path] = []
    monkeypatch.setattr(publisher, "_overlay", lambda _src, dest: overlay_calls.append(dest))

    with pytest.raises(ValueError, match="normalized relative POSIX path"):
        if boundary == "snapshot":
            publisher._snapshot_subtree(winner, agent_path)
        elif boundary == "push":
            publisher.push_branch(
                src_dir=winner,
                branch="optimizer/test",
                base_ref="main",
                message="message",
                agent_path=agent_path,
            )
        else:
            publisher.publish(
                winner_dir=winner,
                branch="optimizer/test",
                base_ref="main",
                title="title",
                body="body",
                agent_path=agent_path,
            )

    assert publisher.calls == []
    assert overlay_calls == []


def test_clone_agent_repo_parses_fragment_and_depth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        calls.append((cmd, kwargs))

        class _R:
            stdout = "main\n"

        return _R()

    monkeypatch.setattr(repo.subprocess, "run", fake_run)
    src = clone_agent_repo("ssh://git@h/g/r.git@main#pkg/agent", tmp_path / "dest", clone_depth=2)
    assert src == AgentSource(repo_url="ssh://git@h/g/r.git", ref="main", agent_path="pkg/agent")
    clone, clone_kwargs = next(call for call in calls if call[0][:2] == ["git", "clone"])
    assert "--depth" in clone and clone[clone.index("--depth") + 1] == "2"
    # the #fragment is stripped from the clone URL (only repo+ref reach git clone)
    assert "ssh://git@h/g/r.git" in clone and "pkg/agent" not in " ".join(clone)
    assert clone_kwargs["capture_output"] is True
    assert clone_kwargs["text"] is True
    assert clone_kwargs["stdin"] is repo.subprocess.DEVNULL


def test_clone_failure_includes_git_stderr_with_redacted_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        f"#!{sys.executable}\nimport os\nos.write(2, b'fatal: repository not found')\nraise SystemExit(128)\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    source = "https://token-user:secret-token@gitlab.com/org/repo.git"  # trufflehog:ignore

    with pytest.raises(AgentCloneError) as exc_info:
        clone_agent_repo(source, tmp_path / "dest")

    message = str(exc_info.value)
    assert "git clone failed" in message
    assert "exit status 128" in message
    assert "https://***@gitlab.com/org/repo.git" in message
    assert "fatal: repository not found" in message
    assert "secret-token" not in message


def test_clone_timeout_redacts_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = "ssh://deploy-token@github.com/org/repo.git"

    def _timeout(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise repo.subprocess.TimeoutExpired(["git", "clone", remote], repo._COMMAND_TIMEOUT)

    monkeypatch.setattr(repo.subprocess, "run", _timeout)

    with pytest.raises(AgentCloneError) as exc_info:
        clone_agent_repo(remote, tmp_path / "dest")

    message = str(exc_info.value)
    assert "git clone timed out after 120s for ssh://***@github.com/org/repo.git" in message
    assert "deploy-token" not in message


def test_clone_agent_repo_redacts_credentials_in_repo_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        repo.subprocess,
        "run",
        lambda *_args, **_kwargs: repo.subprocess.CompletedProcess(args=[], returncode=0, stdout="main\n"),
    )

    source = clone_agent_repo("https://gitlab.com/org/repo.git", tmp_path / "dest")
    assert source.repo_url == "https://gitlab.com/org/repo.git"

    source = clone_agent_repo("https://oauth2:token@gitlab.com/org/repo.git", tmp_path / "dest")  # trufflehog:ignore
    assert source.repo_url == "https://***@gitlab.com/org/repo.git"


# ---------------------------------------------------------------------------
# PRPublisher.push_branch — per-candidate archival (skip-if-exists, subtree)
# ---------------------------------------------------------------------------


def test_push_branch_archives_candidate(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    (agent_dir / "pkg" / "agent").mkdir(parents=True)
    pub = _StubPublisher(agent_dir=agent_dir, origin="ssh://git@h/g/r.git", status=" M main.py")
    pushed = pub.push_branch(
        src_dir=_winner(tmp_path),
        branch="optimizer/run-1/agent-2",
        base_ref="main",
        message="archive agent-2",
        agent_path="pkg/agent",
    )
    assert pushed is True
    push = next(c for c in pub.calls if c[:2] == ["git", "push"])
    assert "optimizer/run-1/agent-2" in push and "--force-with-lease" not in push  # no force for archival
    assert ["git", "ls-remote", "--heads", "origin", "optimizer/run-1/agent-2"] in pub.calls
    assert ["git", "fetch", "origin", "main"] in pub.calls
    assert [
        "git",
        "--literal-pathspecs",
        "rm",
        "-r",
        "-q",
        "-f",
        "--ignore-unmatch",
        "--",
        "pkg/agent",
    ] in pub.calls
    assert (agent_dir / "pkg" / "agent" / "main.py").read_text() == "print('improved')\n"
    assert not (agent_dir / "pkg" / "agent" / "metadata.json").exists()  # generated file excluded


def test_snapshot_subtree_recreates_removed_nested_destination_with_real_git(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    _git(checkout, "init", "-q")

    old_file = checkout / "pkg" / "agent" / "old.py"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("old\n", encoding="utf-8")
    _git(checkout, "add", "pkg/agent/old.py")
    stale = checkout / "pkg" / "agent" / "local-secret.txt"
    stale.write_text("must not survive\n", encoding="utf-8")
    (checkout / "pkg" / "agent" / "metadata.json").write_text("must not survive\n", encoding="utf-8")

    PRPublisher(agent_dir=checkout)._snapshot_subtree(_winner(tmp_path), "pkg/agent")

    assert not old_file.exists()
    assert not stale.exists()
    assert not (checkout / "pkg" / "agent" / "metadata.json").exists()
    assert (checkout / "pkg" / "agent" / "main.py").read_text(encoding="utf-8") == "print('improved')\n"
    assert _git(checkout, "ls-files") == ["pkg/agent/main.py"]


def test_snapshot_subtree_rejects_symlink_ancestor_before_commands_or_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    (checkout / "pkg").symlink_to(outside, target_is_directory=True)
    publisher = PRPublisher(agent_dir=checkout)
    commands: list[list[str]] = []
    monkeypatch.setattr(publisher, "_run", lambda command, **_kwargs: commands.append(command))

    with pytest.raises(ValueError) as exc_info:
        publisher._snapshot_subtree(_winner(tmp_path), "pkg/agent")

    assert str(exc_info.value) == "agent path must stay within the checkout without symlinks"
    assert commands == []
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert not (outside / "agent" / "main.py").exists()


def test_snapshot_subtree_rechecks_path_after_removal_before_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "repo"
    target = checkout / "pkg" / "agent"
    target.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    publisher = PRPublisher(agent_dir=checkout)

    def replace_ancestor_after_remove(command: list[str], **_kwargs: object) -> str:
        if "rm" in command:
            shutil.rmtree(checkout / "pkg")
            (checkout / "pkg").symlink_to(outside, target_is_directory=True)
        return ""

    monkeypatch.setattr(publisher, "_run", replace_ancestor_after_remove)

    with pytest.raises(ValueError, match="stay within the checkout without symlinks"):
        publisher._snapshot_subtree(_winner(tmp_path), "pkg/agent")

    assert not (outside / "agent" / "main.py").exists()


def test_push_branch_scopes_snapshot_status_and_commit_to_agent_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    checkout = tmp_path / "repo"
    checkout.mkdir()
    _git(checkout, "init", "-q")
    (checkout / "pkg" / "agent").mkdir(parents=True)
    (checkout / "pkg" / "agent" / "old.py").write_text("old\n", encoding="utf-8")
    unrelated = checkout / "unrelated.txt"
    unrelated.write_text("base\n", encoding="utf-8")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "base")
    unrelated.write_text("staged unrelated\n", encoding="utf-8")
    _git(checkout, "add", "unrelated.txt")
    (checkout / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    pushes: list[str] = []

    class _LocalPublisher(PRPublisher):
        def _run(self, cmd: list[str], *, cwd: Path | None = None) -> str:
            if cmd[:4] == ["git", "remote", "get-url", "origin"]:
                return "https://github.com/org/repo.git"
            if cmd[:2] == ["git", "ls-remote"]:
                return ""
            if cmd[:2] in (["git", "fetch"], ["git", "checkout"], ["git", "push"]):
                if cmd[:2] == ["git", "push"]:
                    pushes.append(cmd[-1])
                return ""
            return super()._run(cmd, cwd=cwd)

    publisher = _LocalPublisher(agent_dir=checkout)
    pushed = publisher.push_branch(
        src_dir=_winner(tmp_path),
        branch="optimizer/test",
        base_ref="main",
        message="candidate",
        agent_path="pkg/agent",
    )

    assert pushed is True
    assert _git(checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD") == [
        "pkg/agent/main.py",
        "pkg/agent/old.py",
    ]
    assert _git(checkout, "diff", "--cached", "--name-only") == ["unrelated.txt"]
    assert _git(checkout, "status", "--porcelain") == ["M  unrelated.txt", "?? untracked.txt"]
    assert pushes == ["optimizer/test"]

    skipped = publisher.push_branch(
        src_dir=tmp_path / "winner",
        branch="optimizer/identical",
        base_ref="main",
        message="identical",
        agent_path="pkg/agent",
    )
    assert skipped is False
    assert pushes == ["optimizer/test"]


def test_push_branch_skips_when_branch_exists(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    # ls-remote reports the target branch already on origin -> skip (no push), returns False.
    pub = _StubPublisher(
        agent_dir=agent_dir, origin="ssh://git@h/g/r.git", status=" M f", branches=("main", "optimizer/run-1/agent-2")
    )
    assert (
        pub.push_branch(src_dir=_winner(tmp_path), branch="optimizer/run-1/agent-2", base_ref="main", message="m")
        is False
    )
    assert not any(c[:2] == ["git", "push"] for c in pub.calls)


def test_push_branch_skips_empty_diff(tmp_path: Path) -> None:
    agent_dir = tmp_path / "clone"
    agent_dir.mkdir()
    # git status returns empty (candidate identical to base) -> no commit/push, returns False.
    pub = _StubPublisher(agent_dir=agent_dir, origin="ssh://git@h/g/r.git", status="")
    assert (
        pub.push_branch(src_dir=_winner(tmp_path), branch="optimizer/run-1/agent-3", base_ref="main", message="m")
        is False
    )
    assert not any(c[:2] == ["git", "push"] for c in pub.calls)
