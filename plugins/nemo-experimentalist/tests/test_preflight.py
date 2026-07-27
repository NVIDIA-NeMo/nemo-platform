# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import nemo_experimentalist_plugin.preflight as preflight
import pytest
from nemo_experimentalist_plugin.preflight import (
    Probes,
    _default_http_ok,
    _default_run_cmd,
    check_artifacts,
    check_datasets,
    check_environment,
    check_profile,
)
from nemo_experimentalist_plugin.profile import load_profile
from nemo_insights_plugin.contracts.checks import CheckResult, required_failures


def make_probes(*, cmd_ok: bool = True, http: bool = True, env: dict | None = None) -> Probes:
    return Probes(
        run_cmd=lambda argv: (0, "ok") if cmd_ok else (1, "boom"),
        http_ok=lambda url: http,
        env=env or {},
    )


def full_profile(tmp_path: Path, *, agent_source: str | None = None):
    tt = tmp_path / "evals" / "task_template"
    tt.mkdir(parents=True)
    (tt / "task.toml").write_text('[task]\nname = "org/agent__template"\n', encoding="utf-8")
    (tt / "instruction.md").write_text("do the thing", encoding="utf-8")
    for sub in ("evals/train", "evals/val"):
        (tmp_path / sub).mkdir(parents=True)
    body = (
        "agent: a\ntask_template: ./evals/task_template\ndatasets:\n  train: ./evals/train\n  validation: ./evals/val\n"
    )
    if agent_source is not None:
        body += f'agent_source: "{agent_source}"\n'
    (tmp_path / "optimizer.yaml").write_text(body, encoding="utf-8")
    return load_profile(tmp_path / "optimizer.yaml")


def test_preflight_results_use_shared_check_result() -> None:
    result = check_profile(None, None)[0]

    assert type(result) is CheckResult


def test_healthy_experiment_setup_all_pass(tmp_path: Path) -> None:
    probes = make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"})
    profile = full_profile(tmp_path)
    results = (
        check_profile(profile, None)
        + check_environment(profile=profile, insight=None, base_url="http://localhost:8080", probes=probes)
        + check_artifacts(profile, probes=probes)
        + check_datasets(profile)
    )
    assert results and all(r.status == "pass" for r in results)
    assert required_failures(results) == []


def test_missing_profile_is_required_failure() -> None:
    results = check_profile(None, None)
    fails = required_failures(results)
    assert any(r.group == "profile" for r in fails)
    assert any("optimizer.yaml" in (r.hint or "") for r in fails)


def test_bad_task_toml_fails_artifacts(tmp_path: Path) -> None:
    profile = full_profile(tmp_path)
    (tmp_path / "evals" / "task_template" / "task.toml").write_text('[task]\nname = "bare-name"\n', encoding="utf-8")
    results = check_artifacts(profile, probes=make_probes())
    assert any(r.status == "fail" and "org/name" in r.message for r in results)


@pytest.mark.parametrize(
    "content",
    [
        'task = "not-a-table"\n',
        "task = []\n",
        "[task]\nname = 42\n",
    ],
    ids=["scalar-task", "list-task", "non-string-name"],
)
def test_task_toml_schema_invalid_is_required_failure(tmp_path: Path, content: str) -> None:
    profile = full_profile(tmp_path)
    (tmp_path / "evals" / "task_template" / "task.toml").write_text(content, encoding="utf-8")

    results = check_artifacts(profile, probes=make_probes())

    task_toml = next(r for r in results if r.name == "task-toml")
    assert task_toml.status == "fail"
    assert task_toml.severity == "required"
    assert "org/name" in task_toml.message


def test_docker_down_is_required_failure(tmp_path: Path) -> None:
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=None,
        base_url="http://x",
        probes=make_probes(cmd_ok=False),
    )
    assert any(r.severity == "required" and r.status == "fail" and "docker" in r.name for r in results)


def test_unreachable_platform_is_advisory(tmp_path: Path) -> None:
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=None,
        base_url="http://x",
        probes=make_probes(http=False, env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    assert any(r.name == "platform-reachable" and r.status == "warn" for r in results)
    assert all(r.severity == "advisory" for r in results if r.status != "pass")


def test_environment_display_urls_are_sanitized_without_changing_probes(tmp_path: Path) -> None:
    model_base = "https://model-user:model-secret@models.example:8443/v1"  # trufflehog:ignore
    model_probe = f"{model_base}/models"
    platform_base = "https://platform-user:platform-secret@platform.example:9443/api"  # trufflehog:ignore
    probed_urls: list[str] = []

    def http_ok(url: str) -> bool:
        probed_urls.append(url)
        return url == model_probe

    results = check_environment(
        profile=full_profile(tmp_path),
        insight=None,
        base_url=platform_base,
        probes=Probes(
            run_cmd=lambda argv: (0, "ok"),
            http_ok=http_ok,
            env={"EXPERIMENTALIST_API_BASE": model_base, "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )

    model = next(result for result in results if result.name == "model-endpoint")
    platform = next(result for result in results if result.name == "platform-reachable")
    assert probed_urls == [model_probe, f"{platform_base}/health/ready"]
    assert model.message == "https://***@models.example:8443/v1/models reachable"
    assert platform.message == "https://***@platform.example:9443/api unreachable"
    assert not any(
        secret in f"{model.message}\n{platform.message}"
        for secret in ("model-user", "model-secret", "platform-user", "platform-secret")
    )


def test_missing_experiment_credentials_are_required(tmp_path: Path) -> None:
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=None,
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "   "}),  # whitespace-only = unset
    )
    assert any(r.name == "EXPERIMENTALIST_API_BASE" and r.status == "fail" for r in results)
    assert any(r.name == "EXPERIMENTALIST_API_KEY" and r.status == "fail" for r in results)
    assert not any(r.name == "INFERENCE_API_KEY" for r in results)


def test_git_source_probe_failure_is_advisory(tmp_path: Path) -> None:
    def remote_unreachable(argv: list[str]) -> tuple[int, str]:
        return (0, "git version 2") if argv == ["git", "--version"] else (1, "remote unavailable")

    results = check_artifacts(
        full_profile(tmp_path, agent_source="https://host/g/repo.git@main"),
        probes=Probes(run_cmd=remote_unreachable, http_ok=lambda url: True, env={}),
    )
    git = next(r for r in results if r.name == "agent-source-git")
    assert git.severity == "advisory"
    assert git.status == "warn"
    assert "clone" in (git.hint or "")
    assert required_failures(results) == []


@pytest.mark.parametrize(
    ("agent_source", "storage"),
    [
        ("https://host/g/repo.git@main", {}),
        (".", {"archive_candidates": True}),
        (".", {"publish_winner": True}),
    ],
    ids=["git-source", "archive", "publish"],
)
def test_missing_git_is_required_for_effective_source_or_storage(
    tmp_path: Path,
    agent_source: str,
    storage: dict[str, bool],
) -> None:
    def missing_git(argv: list[str]) -> tuple[int, str]:
        if argv == ["git", "--version"]:
            return 127, "git not found"
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path, agent_source=agent_source),
        probes=Probes(run_cmd=missing_git, http_ok=lambda url: True, env={}),
        storage=storage,
    )

    git = next(result for result in results if result.name == "git-installed")
    assert git.status == "fail"
    assert git.severity == "required"
    assert "install git" in (git.hint or "")


def test_local_agent_source_dir_stays_required(tmp_path: Path) -> None:
    results = check_artifacts(full_profile(tmp_path, agent_source="./no/such/dir"), probes=make_probes())
    src = next(r for r in results if r.name == "agent-source-dir")
    assert src.severity == "required"
    assert src.status == "fail"


@pytest.mark.parametrize(
    ("source", "expected_repo"),
    [
        ("https://host/g/repo.git@main#agents/x", "https://host/g/repo.git"),
        ("ssh://git@host/g/repo.git@v1", "ssh://git@host/g/repo.git"),
        ("https://token@host/g/repo.git", "https://token@host/g/repo.git"),
        ("git@host:g/repo.git", "git@host:g/repo.git"),
    ],
)
def test_git_repo_url_extraction(tmp_path: Path, source: str, expected_repo: str) -> None:
    calls: list[list[str]] = []

    def record(argv: list[str]) -> tuple[int, str]:
        calls.append(list(argv))
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path, agent_source=source),
        probes=Probes(run_cmd=record, http_ok=lambda url: True, env={}),
    )
    assert calls == [["git", "--version"], ["git", "ls-remote", expected_repo]]
    assert all(r.status == "pass" for r in results)


@pytest.mark.parametrize(
    "fragment",
    ["pkg//agent", ":(top,glob)**", "../outside", "pkg/.GiT/hooks"],
    ids=["malformed", "pathspec", "traversal", "git-component"],
)
def test_invalid_git_agent_path_is_required_failure_without_probes_or_echo(
    tmp_path: Path,
    fragment: str,
) -> None:
    calls: list[list[str]] = []

    def record(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path, agent_source=f"https://host/g/repo.git#{fragment}"),
        probes=Probes(run_cmd=record, http_ok=lambda _url: True, env={}),
    )

    failure = next(result for result in results if result.name == "agent-source-path")
    assert failure.status == "fail"
    assert failure.severity == "required"
    assert failure.message == "agent path must be a normalized relative POSIX path"
    assert fragment not in failure.message
    assert calls == []


def test_default_http_ok_never_raises_on_malformed_url() -> None:
    # "\x00" makes httpx raise InvalidURL (not an HTTPError) before any network I/O.
    assert _default_http_ok("http://\x00/models") is False


def test_default_run_cmd_timeout_suppresses_command_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    command = [
        "git",
        "ls-remote",
        "https://token-user:command-secret@github.com/org/repo.git?query-secret#fragment-secret",  # trufflehog:ignore
    ]

    def timeout(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise preflight.subprocess.TimeoutExpired(
            command + ["timeout-command-secret"],
            15,
            output="stdout-secret",
            stderr="stderr-secret",
        )

    monkeypatch.setattr(preflight.subprocess, "run", timeout)

    code, output = _default_run_cmd(command)

    assert (code, output) == (124, "")


def test_default_run_cmd_preserves_missing_executable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(preflight.subprocess, "run", missing)

    assert _default_run_cmd(["git", "--version"]) == (127, "git missing")


def test_git_source_probe_timeout_uses_controlled_message(tmp_path: Path) -> None:
    source = "https://token-user:remote-secret@github.com/org/repo.git"  # trufflehog:ignore

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        if argv == ["git", "--version"]:
            return 0, "git version"
        return 124, "child-output-secret"

    results = check_artifacts(
        full_profile(tmp_path, agent_source=source),
        probes=Probes(run_cmd=run_cmd, http_ok=lambda url: True, env={}),
    )

    failure = next(result for result in results if result.name == "agent-source-git")
    assert failure.message == "git ls-remote timed out for https://***@github.com/org/repo.git"


def test_unreadable_task_toml_is_required_failure(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("permission bits are ignored when running as root")
    profile = full_profile(tmp_path)
    toml_path = tmp_path / "evals" / "task_template" / "task.toml"
    toml_path.chmod(0o000)
    try:
        results = check_artifacts(profile, probes=make_probes())
    finally:
        toml_path.chmod(0o644)
    toml = next(r for r in results if r.name == "task-toml")
    assert toml.status == "fail"
    assert toml.severity == "required"
    assert "Permission denied" in toml.message


def test_invalid_utf8_task_toml_is_required_failure(tmp_path: Path) -> None:
    profile = full_profile(tmp_path)
    toml_path = tmp_path / "evals" / "task_template" / "task.toml"
    toml_path.write_bytes(b"[task]\nname = \xff\n")

    results = check_artifacts(profile, probes=make_probes())

    toml = next(result for result in results if result.name == "task-toml")
    assert toml.status == "fail"
    assert toml.severity == "required"
    assert "task.toml unreadable or does not parse" in toml.message
    assert "readable UTF-8 TOML" in (toml.hint or "")


def test_unreadable_insight_file_is_required_failure(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("permission bits are ignored when running as root")
    insight = tmp_path / "insight.yaml"
    insight.write_text("k: v\n", encoding="utf-8")
    insight.chmod(0o000)
    try:
        results = check_environment(
            profile=full_profile(tmp_path),
            insight=str(insight),
            base_url="http://x",
            probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
        )
    finally:
        insight.chmod(0o644)
    r = next(r for r in results if r.name == "insight-file")
    assert r.status == "fail"
    assert r.severity == "required"
    assert "Permission denied" in r.message


def test_non_json_insight_content_is_required_failure(tmp_path: Path) -> None:
    insight = tmp_path / "insights.yaml"
    insight.write_text(
        "insights:\n"
        "  - {id: good, title: Good, agent: a}\n"
        "  - {id: dated, title: Dated, agent: a, observed_at: 2026-07-14}\n",
        encoding="utf-8",
    )
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=str(insight),
        insight_id="0",
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    failure = next(r for r in required_failures(results) if r.name == "insight-file")
    assert "JSON-serializable" in failure.message


def test_pr_cli_auth_uses_effective_storage_over_profile(tmp_path: Path) -> None:
    # Effective (resolved) storage from the auto path wins: publish enabled via
    # --config fires the advisory even though the profile has no experiment_config.
    profile = full_profile(tmp_path, agent_source="https://github.com/org/repo.git")
    results = check_artifacts(profile, probes=make_probes(cmd_ok=False), storage={"publish_winner": True})
    auth = next(r for r in results if r.name == "pr-cli-auth")
    assert auth.status == "warn"
    # And the inverse: effective storage disabling publish suppresses the check
    # even when the profile would have enabled it (storage={} beats profile flags).
    quiet = check_artifacts(profile, probes=make_probes(cmd_ok=False), storage={"publish_winner": False})
    assert not any(r.name == "pr-cli-auth" for r in quiet)


def test_pr_cli_auth_reads_path_form_experiment_config(tmp_path: Path) -> None:
    # Doctor path (no effective storage): a str-path experiment_config that
    # enables publishing must still trigger the advisory.
    profile = full_profile(tmp_path)
    (tmp_path / "exp.yaml").write_text("storage:\n  publish_winner: true\n", encoding="utf-8")
    body = (
        "agent: a\ntask_template: ./evals/task_template\n"
        "datasets:\n  train: ./evals/train\n  validation: ./evals/val\n"
        'agent_source: "https://github.com/org/repo.git"\n'
        "experiment_config: ./exp.yaml\n"
    )
    (tmp_path / "optimizer.yaml").write_text(body, encoding="utf-8")
    profile = load_profile(tmp_path / "optimizer.yaml")
    results = check_artifacts(profile, probes=make_probes(cmd_ok=False))
    auth = next(r for r in results if r.name == "pr-cli-auth")
    assert auth.status == "warn"


@pytest.mark.parametrize(
    ("source", "required_cli", "source_host", "authenticated"),
    [
        ("https://github.com/org/repo.git", "gh", "github.com", False),
        (
            "git@gitlab.example.com:org/repo.git",
            "glab",
            "gitlab.example.com",
            False,
        ),
        ("git@github.com:org/repo.git", "gh", "github.com", True),
        (
            "ssh://git@gitlab.example.com:12051/org/repo.git",
            "glab",
            "gitlab.example.com",
            True,
        ),
    ],
)
def test_forge_auth_checks_matching_cli_and_host(
    tmp_path: Path,
    source: str,
    required_cli: str,
    source_host: str,
    authenticated: bool,
) -> None:
    calls: list[list[str]] = []
    auth_command = [required_cli, "auth", "status", "--hostname", source_host]
    hostless_auth_command = [required_cli, "auth", "status"]
    wrong_cli = "glab" if required_cli == "gh" else "gh"

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        if (
            argv[:2] == ["git", "ls-remote"]
            or argv[0] == wrong_cli
            or argv == hostless_auth_command
            or (authenticated and argv == auth_command)
        ):
            return 0, "ok"
        return 1, "not authenticated"

    results = check_artifacts(
        full_profile(tmp_path, agent_source=source),
        probes=Probes(run_cmd=run_cmd, http_ok=lambda url: True, env={}),
        storage={"publish_winner": True},
    )

    auth = next(r for r in results if r.name == "pr-cli-auth")
    assert auth.status == ("pass" if authenticated else "warn")
    assert auth_command in calls
    assert hostless_auth_command not in calls
    assert not any(call[0] == wrong_cli for call in calls)


def test_forge_auth_unknown_host_is_actionable_advisory(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path, agent_source="https://bitbucket.org/org/repo.git"),
        probes=Probes(run_cmd=run_cmd, http_ok=lambda url: True, env={}),
        storage={"publish_winner": True},
    )

    auth = next(r for r in results if r.name == "pr-cli-auth")
    assert auth.status == "warn"
    assert "unsupported" in auth.message
    assert "GitHub or GitLab" in (auth.hint or "")
    assert not any(call[0] in {"gh", "glab"} for call in calls)


@pytest.mark.parametrize(
    "storage",
    [
        {"publish_winner": True},
        {"archive_candidates": True},
    ],
    ids=["publish-winner", "archive-candidates"],
)
def test_local_persistence_requires_git_source(tmp_path: Path, storage: dict[str, bool]) -> None:
    calls: list[list[str]] = []

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path),
        probes=Probes(run_cmd=run_cmd, http_ok=lambda url: True, env={}),
        storage=storage,
    )

    persistence = next(r for r in results if r.name == "remote-persistence")
    assert persistence.status == "warn"
    assert persistence.severity == "advisory"
    assert "git URL" in persistence.message
    assert "agent_source" in (persistence.hint or "")
    assert calls == [["git", "--version"]]


def test_archive_candidates_alone_does_not_check_forge_auth(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return 0, "ok"

    results = check_artifacts(
        full_profile(tmp_path, agent_source="https://github.com/org/repo.git"),
        probes=Probes(run_cmd=run_cmd, http_ok=lambda url: True, env={}),
        storage={"archive_candidates": True},
    )

    assert not any(r.name == "pr-cli-auth" for r in results)
    assert not any(call[0] in {"gh", "glab"} for call in calls)


def test_preflight_git_failure_suppresses_child_output_and_sanitizes_remote(tmp_path: Path) -> None:
    secret_output = (
        "fatal: https://output-token:output-secret@github.com/org/repo.git"  # trufflehog:ignore
        "?output-query-secret#output-fragment-secret"
    )
    source = "ssh://deploy-token@github.com/org/repo.git"

    def run_cmd(argv: list[str]) -> tuple[int, str]:
        if argv == ["git", "--version"]:
            return 0, "git version"
        return 23, secret_output

    results = check_artifacts(
        full_profile(tmp_path, agent_source=source),
        probes=Probes(
            run_cmd=run_cmd,
            http_ok=lambda url: True,
            env={},
        ),
    )

    failure = next(result for result in results if result.name == "agent-source-git")
    assert failure.message == "git ls-remote failed for ssh://***@github.com/org/repo.git (exit status 23)"


def test_require_template_false_skips_template_checks(tmp_path: Path) -> None:
    # Insight-less runs never read the template: a missing template dir must
    # not fail the artifacts group when require_template=False.
    profile = full_profile(tmp_path)
    (tmp_path / "optimizer.yaml").write_text(
        "agent: a\ntask_template: ./no/such/dir\ndatasets:\n  train: ./evals/train\n  validation: ./evals/val\n",
        encoding="utf-8",
    )
    profile = load_profile(tmp_path / "optimizer.yaml")
    skipped = check_artifacts(profile, probes=make_probes(), require_template=False)
    assert not any(r.name.startswith("task-t") for r in skipped)
    assert required_failures(skipped) == []
    checked = check_artifacts(profile, probes=make_probes())
    assert any(r.name == "task-template-dir" and r.status == "fail" for r in checked)


def test_local_multi_insight_requires_selector(tmp_path: Path) -> None:
    insights = tmp_path / "insights.yaml"
    insights.write_text(
        "insights:\n  - {id: i-a, title: A, agent: a}\n  - {id: i-b, title: B, agent: other}\n",
        encoding="utf-8",
    )
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=str(insights),
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    failure = next(r for r in results if r.name == "insight-file")
    assert failure.status == "fail" and failure.severity == "required"
    assert "--insight-id" in failure.message
    assert not any(r.name == "insight-agent" for r in results)


def test_single_insight_file_with_matching_selector_passes(tmp_path: Path) -> None:
    insights = tmp_path / "insights.yaml"
    insights.write_text("insights:\n  - {id: i-a, title: A, agent: a}\n", encoding="utf-8")
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=str(insights),
        insight_id="i-a",
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    parse = next(r for r in results if r.name == "insight-file")
    assert parse.status == "pass"
    assert required_failures(results) == []


def test_selected_insight_checks_only_selected_agent_without_selector_warning(tmp_path: Path) -> None:
    insights = tmp_path / "insights.yaml"
    insights.write_text(
        "insights:\n  - {id: i-a, title: A, agent: a}\n  - {id: i-b, title: B, agent: other}\n",
        encoding="utf-8",
    )
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=str(insights),
        insight_id="i-a",
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    agent = next(r for r in results if r.name == "insight-agent")
    assert agent.status == "pass"
    assert not any(r.name == "insight-selector" for r in results)
    assert required_failures(results) == []


def test_ambiguous_selected_insight_is_required_failure(tmp_path: Path) -> None:
    insights = tmp_path / "insights.yaml"
    insights.write_text(
        "insights:\n  - {id: i-a, title: same, agent: a}\n  - {id: i-b, title: same, agent: a}\n",
        encoding="utf-8",
    )
    results = check_environment(
        profile=full_profile(tmp_path),
        insight=str(insights),
        insight_id="same",
        base_url="http://x",
        probes=make_probes(env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"}),
    )
    failure = next(r for r in required_failures(results) if r.name == "insight-file")
    assert "ambiguous" in failure.message


def test_bare_dataset_name_matching_local_directory_is_local_path(tmp_path: Path) -> None:
    profile = full_profile(tmp_path)
    (tmp_path / "mydata").mkdir()
    (tmp_path / "optimizer.yaml").write_text(
        "agent: a\ntask_template: ./evals/task_template\ndatasets:\n  train: mydata\n  validation: ./evals/val\n",
        encoding="utf-8",
    )
    profile = load_profile(tmp_path / "optimizer.yaml")
    results = check_datasets(profile)
    train = next(r for r in results if r.name == "dataset-train")
    assert train.status == "pass" and str(tmp_path / "mydata") in train.message


def test_doctor_rejects_local_dataset_file(tmp_path: Path) -> None:
    full_profile(tmp_path)
    dataset_file = tmp_path / "train.jsonl"
    dataset_file.write_text("{}\n", encoding="utf-8")
    (tmp_path / "optimizer.yaml").write_text(
        "agent: a\ntask_template: ./evals/task_template\n"
        "datasets:\n  train: ./train.jsonl\n  validation: ./evals/val\n",
        encoding="utf-8",
    )

    results = check_datasets(load_profile(tmp_path / "optimizer.yaml"))

    train = next(result for result in results if result.name == "dataset-train")
    assert train.status == "fail"
    assert "not a directory" in train.message


def test_check_artifacts_has_no_dataset_results(tmp_path: Path) -> None:
    # Pins the review deletion: the experiment flow's resolved dataset URIs are
    # proven-existing by construction, so check_artifacts never validates
    # datasets — that lives only in check_datasets (doctor).
    results = check_artifacts(full_profile(tmp_path), probes=make_probes())
    assert not any(r.name.startswith("dataset-") for r in results)


def test_missing_env_hint_names_source_and_env_file(tmp_path: Path) -> None:
    profile = full_profile(tmp_path)
    results = check_environment(
        profile=profile,
        insight=None,
        base_url="http://x",
        probes=make_probes(env={}),
    )
    base = next(r for r in results if r.name == "EXPERIMENTALIST_API_BASE")
    assert "inference-api.nvidia.com" in (base.hint or "")  # names the real endpoint
    assert str(tmp_path / ".env") in (base.hint or "")  # says exactly where to save it
    assert ".env.example" in (base.hint or "")
    assert "export EXPERIMENTALIST_API_BASE" in (base.hint or "")
