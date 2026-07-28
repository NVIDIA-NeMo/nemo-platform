# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI profile-driven behavior for experiment."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from nemo_experimentalist_plugin import cli
from nemo_experimentalist_plugin.preflight import Probes
from nemo_insights_plugin.contracts.profile import DEFAULT_BASE_URL
from typer.testing import CliRunner

runner = CliRunner()


def quiet_probes(env: dict | None = None) -> Probes:
    return Probes(
        run_cmd=lambda argv: (0, "ok"),
        http_ok=lambda url: True,
        env=env
        or {
            "EXPERIMENTALIST_API_BASE": "http://llm",
            "EXPERIMENTALIST_API_KEY": "k",
            "INFERENCE_API_KEY": "k",
        },
    )


def write_task_toml(profile_tree: Path) -> None:
    (profile_tree / "evals" / "task_template" / "task.toml").write_text('[task]\nname = "org/x__t"\n', encoding="utf-8")


@pytest.fixture(autouse=True)
def _quiet_preflight(monkeypatch):
    """Deterministic probes for every test; tests override with their own
    monkeypatch.setattr when they exercise specific probe behavior."""
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    monkeypatch.setattr(cli, "_CONTAINER_RUNTIME", True)


@dataclass
class FakePlatformClient:
    base_url: str
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_platform_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "make_client", FakePlatformClient)


@pytest.fixture()
def app():
    return cli.ExperimentalistCLI().get_cli()


@pytest.fixture()
def profile_tree(tmp_path: Path) -> Path:
    for sub in ("evals/task_template", "evals/train", "evals/val"):
        (tmp_path / sub).mkdir(parents=True)
    (tmp_path / "optimizer.yaml").write_text(
        "agent: flight-planner\n"
        "task_template: ./evals/task_template\n"
        "datasets:\n  train: ./evals/train\n  validation: ./evals/val\n",
        encoding="utf-8",
    )
    return tmp_path


class RunRecorder:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    async def __call__(self, **kwargs) -> str:
        self.kwargs = kwargs
        return "ok"


def test_experiment_insight_only_with_profile(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "out")])
    assert result.exit_code == 0, result.output
    assert recorder.kwargs["insight"] == "ins-1"
    assert recorder.kwargs["train_dataset"].uri == str((profile_tree / "evals" / "train").resolve())
    assert recorder.kwargs["agent"] == str(profile_tree.resolve())


def test_experiment_explicit_profile_flag(app, profile_tree: Path, monkeypatch, tmp_path: Path) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(
        app,
        [
            "run",
            "--insight",
            "ins-1",
            "--profile",
            str(profile_tree / "optimizer.yaml"),
            "-o",
            str(elsewhere / "o"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert recorder.kwargs["workspace"] == "default"


def test_experiment_no_profile_missing_flags_errors_with_skeleton(app, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(tmp_path / "o")])
    assert result.exit_code == 1
    assert "optimizer.yaml" in result.output
    assert "--train-dataset" in result.output


def test_experiment_all_flags_no_profile_still_works(app, tmp_path: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    for sub in ("agent", "t", "v"):
        (tmp_path / sub).mkdir()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "--agent",
            str(tmp_path / "agent"),
            "--train-dataset",
            str(tmp_path / "t"),
            "--validation-dataset",
            str(tmp_path / "v"),
            "-o",
            str(tmp_path / "o"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert recorder.kwargs["insight"] is None


def test_profileless_experiment_blocks_missing_effective_agent_path(app, tmp_path: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    for sub in ("train", "validation"):
        (tmp_path / sub).mkdir()
    missing_agent = tmp_path / "missing-agent"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "run",
            "--agent",
            str(missing_agent),
            "--train-dataset",
            str(tmp_path / "train"),
            "--validation-dataset",
            str(tmp_path / "validation"),
            "-o",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert recorder.kwargs is None
    assert f"agent source dir missing: {missing_agent}" in result.output


def test_profileless_experiment_blocks_missing_effective_task_template(app, tmp_path: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    for sub in ("agent", "train", "validation"):
        (tmp_path / sub).mkdir()
    missing_template = tmp_path / "missing-template"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "run",
            "--agent",
            str(tmp_path / "agent"),
            "--insight",
            "ins-1",
            "--train-dataset",
            str(tmp_path / "train"),
            "--validation-dataset",
            str(tmp_path / "validation"),
            "--task-template",
            str(missing_template),
            "-o",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert recorder.kwargs is None
    assert f"task_template dir missing: {missing_template}" in result.output


def test_profileless_implicit_experiment_dirs_retry_collisions_and_stay_unique(
    app, tmp_path: Path, monkeypatch
) -> None:
    fixed_now = cli.datetime(2026, 7, 14, 12, 34, 56, tzinfo=cli.UTC)

    class FrozenDateTime:
        @staticmethod
        def now(*, tz):
            assert tz is cli.UTC
            return fixed_now

    collision_hex = "a" * 32
    first_hex = "b" * 32
    second_hex = "c" * 32
    generated_uuids = iter(
        [
            cli.uuid.UUID(hex=collision_hex),
            cli.uuid.UUID(hex=collision_hex),
            cli.uuid.UUID(hex=first_hex),
            cli.uuid.UUID(hex=first_hex),
            cli.uuid.UUID(hex=second_hex),
        ]
    )
    output_root = tmp_path / "tmp"
    colliding_dir = output_root / f"20260714-123456-{collision_hex}"
    colliding_dir.mkdir(parents=True)

    recorder = RunRecorder()
    monkeypatch.setattr(cli, "datetime", FrozenDateTime)
    monkeypatch.setattr(cli.uuid, "uuid4", lambda: next(generated_uuids))
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    for sub in ("agent", "t", "v"):
        (tmp_path / sub).mkdir()
    monkeypatch.chdir(tmp_path)
    args = [
        "run",
        "--agent",
        str(tmp_path / "agent"),
        "--train-dataset",
        str(tmp_path / "t"),
        "--validation-dataset",
        str(tmp_path / "v"),
    ]

    first_result = runner.invoke(app, args)
    first_dir = Path(recorder.kwargs["experiment_dir"])
    second_result = runner.invoke(app, args)
    second_dir = Path(recorder.kwargs["experiment_dir"])

    expected_first = Path("tmp") / f"20260714-123456-{first_hex}"
    expected_second = Path("tmp") / f"20260714-123456-{second_hex}"
    assert first_result.exit_code == 0, first_result.output
    assert second_result.exit_code == 0, second_result.output
    assert first_dir == expected_first
    assert second_dir == expected_second
    assert first_dir != second_dir
    assert (tmp_path / first_dir).is_dir()
    assert (tmp_path / second_dir).is_dir()
    assert f"Experiment dir: {expected_first}" in first_result.output
    assert f"Experiment dir: {expected_second}" in second_result.output


def test_experiment_insight_id_selects_from_analyst_file(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    insights = profile_tree / "insights.yaml"
    items = [
        {"id": "i-a", "title": "A", "description": "d", "agent": "flight-planner", "status": "open", "trace_refs": []},
        {"id": "i-b", "title": "B", "description": "d", "agent": "flight-planner", "status": "open", "trace_refs": []},
    ]
    insights.write_text(json.dumps({"insights": items}), encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        ["run", "--insight", str(insights), "--insight-id", "i-b", "-o", str(profile_tree / "o")],
    )
    assert result.exit_code == 0, result.output
    selected = json.loads(Path(recorder.kwargs["insight"]).read_text(encoding="utf-8"))
    assert selected["id"] == "i-b"


def test_doctor_healthy_exits_zero(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "✓" in result.output


def test_doctor_uses_openshell_by_default(app, profile_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = profile_tree / "optimizer.yaml"
    captured: dict[str, object] = {}

    def launch(
        command: str,
        args: list[str],
        *,
        workspace_dir: Path,
        output_dir: Path | None,
        platform_url: str | None,
    ) -> int:
        captured.update(
            command=command,
            args=args,
            workspace_dir=workspace_dir,
            output_dir=output_dir,
            platform_url=platform_url,
        )
        return 0

    monkeypatch.setattr(cli, "_CONTAINER_RUNTIME", False)
    monkeypatch.setattr(cli, "_OPEN_SHELL_LAUNCHER", launch)
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(
        app,
        [
            "doctor",
            "--profile",
            str(profile_path),
            "--insight",
            "platform-insight-id",
            "--insight-id",
            "selected",
            "--base-url",
            "https://platform.example",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == {
        "command": "doctor",
        "args": [
            "--insight",
            "platform-insight-id",
            "--insight-id",
            "selected",
            "--profile",
            f"/sandbox/project/{profile_tree.name}/optimizer.yaml",
        ],
        "workspace_dir": profile_tree,
        "output_dir": None,
        "platform_url": "https://platform.example",
    }


def test_doctor_no_profile_exits_one_with_skeleton(app, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_PREFLIGHT_PROBES", quiet_probes())
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "optimizer.yaml" in result.output


def test_doctor_invalid_utf8_profile_is_structured_without_traceback(
    app,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "optimizer.yaml").write_bytes(b"agent: \xff\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Profile\n  ✗ Could not parse profile" in result.output
    assert "readable UTF-8 YAML" in result.output
    assert "Traceback" not in result.output


def test_doctor_invalid_utf8_task_toml_is_structured_without_traceback(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (profile_tree / "evals" / "task_template" / "task.toml").write_bytes(b"[task]\nname = \xff\n")
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor", "--insight", "ins-1"])

    assert result.exit_code == 1
    assert "Artifacts\n" in result.output
    assert "✗ task.toml unreadable or does not parse" in result.output
    assert "readable UTF-8 TOML" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "fragment",
    ["pkg//agent", ":(top,glob)**", "../outside"],
    ids=["malformed", "pathspec", "traversal"],
)
def test_doctor_invalid_git_agent_path_is_structured_without_traceback(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    fragment: str,
) -> None:
    profile = profile_tree / "optimizer.yaml"
    profile.write_text(
        profile.read_text(encoding="utf-8") + f'agent_source: "https://host/g/repo.git#{fragment}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "✗ agent path must be a normalized relative POSIX path" in result.output
    assert fragment not in result.output
    assert "Traceback" not in result.output


def test_doctor_redacts_model_and_platform_display_urls(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    model_base = "https://model-user:model-secret@models.example:8443/v1"  # trufflehog:ignore
    platform_base = "https://platform-user:platform-secret@platform.example:9443/api"  # trufflehog:ignore
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        quiet_probes(env={"EXPERIMENTALIST_API_BASE": model_base, "EXPERIMENTALIST_API_KEY": "k"}),
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor", "--base-url", platform_base])

    assert result.exit_code == 0, result.output
    assert "https://***@models.example:8443/v1/models reachable" in result.output
    assert "https://***@platform.example:9443/api reachable" in result.output
    assert not any(
        secret in result.output for secret in ("model-user", "model-secret", "platform-user", "platform-secret")
    )


def test_experiment_hard_fails_on_required_check(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=lambda argv: (1, "docker down"),
            http_ok=lambda url: True,
            env={"EXPERIMENTALIST_API_BASE": "b", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "o")])
    assert result.exit_code == 1
    assert recorder.kwargs is None  # run never started
    assert "✗" in result.output


def test_experiment_advisory_warns_but_runs(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=lambda argv: (0, "ok"),
            http_ok=lambda url: False,  # platform unreachable → advisory
            env={"EXPERIMENTALIST_API_BASE": "b", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "o")])
    assert result.exit_code == 0, result.output
    assert recorder.kwargs is not None  # run proceeded


def test_experiment_effective_storage_requires_git_before_runner(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)

    def missing_git(argv: list[str]) -> tuple[int, str]:
        if argv == ["git", "--version"]:
            return 127, "git not found"
        return 0, "ok"

    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=missing_git,
            http_ok=lambda url: True,
            env={"EXPERIMENTALIST_API_BASE": "b", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    config = profile_tree / "experiment.yaml"
    config.write_text("storage:\n  archive_candidates: true\n", encoding="utf-8")
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(
        app,
        ["run", "--no-insight", "--config", str(config), "-o", str(profile_tree / "o")],
    )

    assert result.exit_code == 1
    assert "'git' is not available" in result.output
    assert recorder.kwargs is None


def test_discovered_profile_is_announced(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "out")])
    assert result.exit_code == 0, result.output
    assert "Using profile:" in result.output
    assert "flight-planner" in result.output


def test_explicit_profile_is_not_announced(app, profile_tree: Path, monkeypatch, tmp_path: Path) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    elsewhere = tmp_path / "elsewhere2"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(
        app,
        [
            "run",
            "--insight",
            "ins-1",
            "--profile",
            str(profile_tree / "optimizer.yaml"),
            "-o",
            str(elsewhere / "o"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Using profile:" not in result.output


def test_missing_creds_reported_before_any_resolution(app, profile_tree: Path, monkeypatch) -> None:
    # Phase-1 ordering: the grouped credentials report must surface even though
    # resolution (whose loop import would raise a bare ValueError) never runs.
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(run_cmd=lambda argv: (0, "ok"), http_ok=lambda url: True, env={}),
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "o")])
    assert result.exit_code == 1
    assert recorder.kwargs is None
    assert "EXPERIMENTALIST_API_BASE" in result.output
    assert "export EXPERIMENTALIST_API_BASE" in result.output  # the hint, not a bare ValueError


def test_insightless_run_skips_template_checks(app, profile_tree: Path, monkeypatch) -> None:
    # profile_tree's template dir has no task.toml — a Mode 2 (no insight) run
    # never reads the template, so preflight must not fail on it.
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "-o", str(profile_tree / "o")])
    assert result.exit_code == 0, result.output
    assert recorder.kwargs is not None
    assert recorder.kwargs["insight"] is None


def test_empty_config_flag_is_an_error_not_silent_fallback(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    empty = profile_tree / "empty.yaml"
    empty.write_text("# comments only\n", encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "--config", str(empty), "-o", str(profile_tree / "o")])
    assert result.exit_code == 1
    assert "is empty" in result.output
    assert recorder.kwargs is None


def test_doctor_multi_insight_file_requires_selector(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    insights = profile_tree / "insights.yaml"
    items = [
        {"id": "i-a", "title": "A", "agent": "flight-planner"},
        {"id": "i-b", "title": "B", "agent": "flight-planner"},
    ]
    insights.write_text(json.dumps({"insights": items}), encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["doctor", "--insight", str(insights)])
    assert result.exit_code == 1
    assert "--insight-id" in result.output


def test_doctor_multi_insight_agent_mismatch_fails(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    insights = profile_tree / "insights.yaml"
    items = [{"id": "i-a", "title": "A", "agent": "someone-else"}]
    insights.write_text(json.dumps({"insights": items}), encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["doctor", "--insight", str(insights)])
    assert result.exit_code == 1
    assert "someone-else" in result.output


def test_profile_dir_env_file_is_loaded_for_experiment(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.delenv("NEMO_OPT_TEST_DOTENV", raising=False)
    (profile_tree / ".env").write_text("NEMO_OPT_TEST_DOTENV=from-env-file\n", encoding="utf-8")
    monkeypatch.chdir(profile_tree)

    try:
        result = runner.invoke(app, ["run", "-o", str(profile_tree / "out")])
        assert result.exit_code == 0, result.output
        assert "Loaded .env" in result.output
        assert os.environ["NEMO_OPT_TEST_DOTENV"] == "from-env-file"
    finally:
        os.environ.pop("NEMO_OPT_TEST_DOTENV", None)


def test_experiment_loads_nmp_base_url_from_profile_env(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.delenv("NMP_BASE_URL", raising=False)
    (profile_tree / ".env").write_text(
        "NMP_BASE_URL=https://platform.example\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(
        app,
        ["run", "--no-insight", "-o", str(profile_tree / "out")],
    )

    assert result.exit_code == 0, result.output
    client = recorder.kwargs["client"]
    assert client.base_url == "https://platform.example"
    assert client.closed


def test_doctor_loads_nmp_base_url_from_profile_env(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    urls: list[str] = []

    def record_http(url: str) -> bool:
        urls.append(url)
        return True

    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=lambda argv: (0, "ok"),
            http_ok=record_http,
            env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    monkeypatch.delenv("NMP_BASE_URL", raising=False)
    (profile_tree / ".env").write_text(
        "NMP_BASE_URL=https://platform.example\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "https://platform.example/health/ready" in urls


def test_default_experiment_dir_is_profile_scoped_and_announced(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1"])
    assert result.exit_code == 0, result.output
    assert "Experiment dir:" in result.output
    experiment_dir = Path(recorder.kwargs["experiment_dir"])
    assert experiment_dir.is_relative_to(profile_tree / ".nemo-optimizer" / "experiments")


def test_default_experiment_dir_retries_collision_and_reserves(app, profile_tree: Path, monkeypatch) -> None:
    fixed_now = cli.datetime(2026, 7, 14, 12, 34, 56, tzinfo=cli.UTC)

    class FrozenDateTime:
        @staticmethod
        def now(*, tz):
            assert tz is cli.UTC
            return fixed_now

    collision_hex = "a" * 32
    unique_hex = "b" * 32
    generated_uuids = iter(
        [
            cli.uuid.UUID(hex=collision_hex),
            cli.uuid.UUID(hex=collision_hex),
            cli.uuid.UUID(hex=unique_hex),
        ]
    )
    experiments_root = profile_tree / ".nemo-optimizer" / "experiments"
    colliding_dir = experiments_root / f"20260714-123456-{collision_hex}"
    colliding_dir.mkdir(parents=True)

    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "datetime", FrozenDateTime)
    monkeypatch.setattr(cli.uuid, "uuid4", lambda: next(generated_uuids))
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["run", "--insight", "ins-1"])

    expected = experiments_root / f"20260714-123456-{unique_hex}"
    assert result.exit_code == 0, result.output
    assert Path(recorder.kwargs["experiment_dir"]) == expected
    assert expected.is_dir()
    assert colliding_dir.is_dir()


def test_default_experiment_dir_is_not_reserved_before_required_preflight(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=lambda argv: (1, "docker down"),
            http_ok=lambda url: True,
            env={"EXPERIMENTALIST_API_BASE": "b", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["run", "--insight", "ins-1"])

    assert result.exit_code == 1
    assert recorder.kwargs is None
    assert not (profile_tree / ".nemo-optimizer" / "experiments").exists()


def test_explicit_experiment_dir_still_wins(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", "ins-1", "-o", str(profile_tree / "custom")])
    assert result.exit_code == 0, result.output
    assert "Experiment dir:" not in result.output
    assert Path(recorder.kwargs["experiment_dir"]) == profile_tree / "custom"


def test_credential_defaults_inference_key_powers_gateway_experiment() -> None:
    env = {"INFERENCE_API_KEY": "sk-gateway"}
    applied = cli._apply_credential_defaults(env)
    assert env["EXPERIMENTALIST_API_BASE"] == "https://inference-api.nvidia.com/v1"
    assert env["EXPERIMENTALIST_API_KEY"] == "sk-gateway"
    assert len(applied) == 2


def test_credential_defaults_never_fill_analyst_key() -> None:
    env = {"EXPERIMENTALIST_API_KEY": "sk-gateway"}
    cli._apply_credential_defaults(env)
    assert "INFERENCE_API_KEY" not in env


def test_credential_defaults_custom_base_never_inherits_gateway_key() -> None:
    custom = {"EXPERIMENTALIST_API_BASE": "https://api.openai.com/v1", "INFERENCE_API_KEY": "sk-gateway"}
    cli._apply_credential_defaults(custom)
    assert "EXPERIMENTALIST_API_KEY" not in custom


def test_credential_defaults_reject_gateway_lookalike_hosts() -> None:
    for base in (
        "https://inference-api.nvidia.com.attacker.example/v1",
        "https://evil-inference-api.nvidia.com/v1",
        "http://inference-api.nvidia.com/v1",
    ):
        env = {"EXPERIMENTALIST_API_BASE": base, "INFERENCE_API_KEY": "sk-secret"}
        cli._apply_credential_defaults(env)
        assert "EXPERIMENTALIST_API_KEY" not in env


def test_credential_defaults_never_override() -> None:
    env = {
        "INFERENCE_API_KEY": "sk-a",
        "EXPERIMENTALIST_API_BASE": "https://inference-api.nvidia.com/v1",
        "EXPERIMENTALIST_API_KEY": "sk-b",
    }
    assert cli._apply_credential_defaults(env) == []
    assert env["EXPERIMENTALIST_API_KEY"] == "sk-b"


def test_experiment_defaults_to_shared_insights_file(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    shared = profile_tree / ".nemo-optimizer" / "insights.yaml"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps({"insights": [{"id": "i-1", "title": "T", "agent": "flight-planner", "trace_refs": []}]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "-o", str(profile_tree / "o")])
    assert result.exit_code == 0, result.output
    assert "Insight file:" in result.output
    selected = json.loads(Path(recorder.kwargs["insight"]).read_text(encoding="utf-8"))
    assert selected["id"] == "i-1"


def test_experiment_selected_insight_uses_shared_default_without_stale_warning(
    app, profile_tree: Path, monkeypatch
) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    shared = profile_tree / ".nemo-optimizer" / "insights.yaml"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps(
            {
                "insights": [
                    {"id": "i-a", "title": "A", "agent": "flight-planner"},
                    {"id": "i-b", "title": "B", "agent": "flight-planner"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        ["run", "--insight-id", "1", "-o", str(profile_tree / "o")],
    )
    assert result.exit_code == 0, result.output
    selected = json.loads(Path(recorder.kwargs["insight"]).read_text(encoding="utf-8"))
    assert selected["id"] == "i-b"
    assert "will require --insight-id" not in result.output


def test_experiment_insight_id_requires_resolved_insight(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        ["run", "--insight-id", "0", "-o", str(profile_tree / "o")],
    )
    assert result.exit_code == 1
    assert "--insight-id" in result.output
    assert "local multi-insight" in result.output
    assert recorder.kwargs is None


def test_experiment_insight_id_rejects_platform_id(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        [
            "run",
            "--insight",
            "ins-platform",
            "--insight-id",
            "0",
            "-o",
            str(profile_tree / "o"),
        ],
    )
    assert result.exit_code == 1
    assert "local multi-insight" in result.output
    assert recorder.kwargs is None


def test_experiment_insight_id_matching_single_local_insight_passes(app, profile_tree: Path, monkeypatch) -> None:
    write_task_toml(profile_tree)
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    single = profile_tree / "insights.yaml"
    single.write_text(
        json.dumps({"insights": [{"id": "i-1", "title": "T", "agent": "flight-planner"}]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        [
            "run",
            "--insight",
            str(single),
            "--insight-id",
            "i-1",
            "-o",
            str(profile_tree / "o"),
        ],
    )
    assert result.exit_code == 0, result.output
    selected = json.loads(Path(recorder.kwargs["insight"]).read_text(encoding="utf-8"))
    assert selected["id"] == "i-1"


def test_experiment_no_insight_skips_existing_shared_default(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    shared = profile_tree / ".nemo-optimizer" / "insights.yaml"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps({"insights": [{"id": "i-1", "title": "T", "agent": "flight-planner"}]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        ["run", "--no-insight", "-o", str(profile_tree / "o")],
    )
    assert result.exit_code == 0, result.output
    assert recorder.kwargs["insight"] is None
    assert "Insight disabled" in result.output
    assert "Insight file:" not in result.output


@pytest.mark.parametrize(
    "insight_args",
    [
        ["--no-insight", "--insight", "ins-1"],
        ["--no-insight", "--insight-id", "0"],
    ],
)
def test_experiment_insight_conflict_is_clean(
    app,
    profile_tree: Path,
    monkeypatch,
    insight_args: list[str],
) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(
        app,
        ["run", *insight_args, "-o", str(profile_tree / "o")],
    )
    assert result.exit_code == 1
    assert "--no-insight cannot be combined" in result.output
    assert recorder.kwargs is None


def test_experiment_insight_id_help_documents_zero_based_index(app) -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0, result.output
    help_text = " ".join(result.output.replace("│", " ").split())
    assert "exact id/title first" in help_text
    assert "zero-based index" in help_text
    assert "local multi-insight" in help_text


def test_experiment_mismatched_insight_blocked_before_resolution(app, profile_tree: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    bad = profile_tree / "insight.json"
    bad.write_text(json.dumps({"id": "i-x", "title": "T", "agent": "someone-else"}), encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    result = runner.invoke(app, ["run", "--insight", str(bad), "-o", str(profile_tree / "o")])
    assert result.exit_code == 1
    assert "someone-else" in result.output
    assert recorder.kwargs is None  # blocked in phase-1 preflight, before resolution


def test_profileless_mode2_without_agent_stops_before_runner(app, tmp_path: Path, monkeypatch) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    for sub in ("train", "validation"):
        (tmp_path / sub).mkdir()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "run",
            "--train-dataset",
            str(tmp_path / "train"),
            "--validation-dataset",
            str(tmp_path / "validation"),
            "-o",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert "--agent" in result.output
    assert recorder.kwargs is None


def test_doctor_validates_implicit_shared_insight_and_selector(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_task_toml(profile_tree)
    shared = profile_tree / ".nemo-optimizer" / "insights.yaml"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps(
            {
                "insights": [
                    {"id": "i-a", "title": "A", "agent": "flight-planner"},
                    {"id": "i-b", "title": "B", "agent": "flight-planner"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)

    unselected = runner.invoke(app, ["doctor"])
    selected = runner.invoke(app, ["doctor", "--insight-id", "i-b"])

    assert unselected.exit_code == 1
    assert "pass --insight-id" in unselected.output
    assert selected.exit_code == 0, selected.output
    assert "2 insights" in selected.output


def test_doctor_validates_implicit_shared_insight_agent(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_task_toml(profile_tree)
    shared = profile_tree / ".nemo-optimizer" / "insights.yaml"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps({"insights": [{"id": "i-x", "title": "Other", "agent": "someone-else"}]}),
        encoding="utf-8",
    )
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "someone-else" in result.output


def test_doctor_validates_effective_agent_spec_readability(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_task_toml(profile_tree)
    spec = profile_tree / "AGENT-SPEC.md"
    spec.write_bytes(b"\xff")
    with (profile_tree / "optimizer.yaml").open("a", encoding="utf-8") as profile_file:
        profile_file.write("agent_spec: ./AGENT-SPEC.md\n")
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Could not read agent_spec" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("config_body", "expected"),
    [
        (None, "Could not read experiment_config"),
        ("storage: [\n", "Could not read experiment_config"),
        ("max_rounds: banana\n", "Invalid experiment config"),
    ],
    ids=["missing", "malformed-yaml", "invalid-value"],
)
def test_doctor_validates_full_effective_experiment_config(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_body: str | None,
    expected: str,
) -> None:
    write_task_toml(profile_tree)
    with (profile_tree / "optimizer.yaml").open("a", encoding="utf-8") as profile_file:
        profile_file.write("experiment_config: ./experiment.yaml\n")
    if config_body is not None:
        (profile_tree / "experiment.yaml").write_text(config_body, encoding="utf-8")
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert expected in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["run", "doctor"])
def test_env_file_encoding_failure_is_clean_and_actionable(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    write_task_toml(profile_tree)
    (profile_tree / ".env").write_bytes(b"NMP_BASE_URL=\xff")
    monkeypatch.chdir(profile_tree)
    args = [command]
    if command == "run":
        args += ["--no-insight", "-o", str(profile_tree / "out")]

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert "Could not read environment file" in result.output
    assert "UTF-8" in result.output
    assert "Traceback" not in result.output


def test_doctor_env_file_permission_failure_is_required_and_actionable(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_task_toml(profile_tree)
    env_file = profile_tree / ".env"
    env_file.write_text("NMP_BASE_URL=https://profile.example\n", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_env_file(path: Path, *args: object, **kwargs: object) -> str:
        if path == env_file:
            raise PermissionError("permission denied by test")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_env_file)
    monkeypatch.chdir(profile_tree)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Could not read environment file" in result.output
    assert "permission denied" in result.output
    assert "check that the file is readable UTF-8" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("explicit", "shell", "profile_env", "expected"),
    [
        ("https://explicit.example", "https://shell.example", "https://profile.example", "https://explicit.example"),
        (None, "https://shell.example", "https://profile.example", "https://shell.example"),
        (None, None, "https://profile.example", "https://profile.example"),
        (None, None, None, DEFAULT_BASE_URL),
    ],
    ids=["explicit", "shell", "profile-env", "default-ignores-nemo"],
)
def test_experiment_nmp_base_url_precedence_and_ignores_nemo_base_url(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit: str | None,
    shell: str | None,
    profile_env: str | None,
    expected: str,
) -> None:
    recorder = RunRecorder()
    monkeypatch.setattr(cli, "run_experimentalist", recorder)
    monkeypatch.setenv("NEMO_BASE_URL", "https://legacy-must-be-ignored.example")
    if shell is None:
        monkeypatch.delenv("NMP_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("NMP_BASE_URL", shell)
    if profile_env is not None:
        (profile_tree / ".env").write_text(f"NMP_BASE_URL={profile_env}\n", encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    args = ["run", "--no-insight", "-o", str(profile_tree / "out")]
    if explicit is not None:
        args += ["--base-url", explicit]

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    client = recorder.kwargs["client"]
    assert client.base_url == expected
    assert client.closed


@pytest.mark.parametrize(
    ("explicit", "shell", "profile_env", "expected"),
    [
        ("https://explicit.example", "https://shell.example", "https://profile.example", "https://explicit.example"),
        (None, "https://shell.example", "https://profile.example", "https://shell.example"),
        (None, None, "https://profile.example", "https://profile.example"),
        (None, None, None, DEFAULT_BASE_URL),
    ],
    ids=["explicit", "shell", "profile-env", "default-ignores-nemo"],
)
def test_doctor_nmp_base_url_precedence_and_ignores_nemo_base_url(
    app,
    profile_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit: str | None,
    shell: str | None,
    profile_env: str | None,
    expected: str,
) -> None:
    write_task_toml(profile_tree)
    urls: list[str] = []
    monkeypatch.setattr(
        cli,
        "_PREFLIGHT_PROBES",
        Probes(
            run_cmd=lambda argv: (0, "ok"),
            http_ok=lambda url: not urls.append(url),
            env={"EXPERIMENTALIST_API_BASE": "http://llm", "EXPERIMENTALIST_API_KEY": "k"},
        ),
    )
    monkeypatch.setenv("NEMO_BASE_URL", "https://legacy-must-be-ignored.example")
    if shell is None:
        monkeypatch.delenv("NMP_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("NMP_BASE_URL", shell)
    if profile_env is not None:
        (profile_tree / ".env").write_text(f"NMP_BASE_URL={profile_env}\n", encoding="utf-8")
    monkeypatch.chdir(profile_tree)
    args = ["doctor"]
    if explicit is not None:
        args += ["--base-url", explicit]

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert urls == ["http://llm/models", f"{expected}/health/ready"]


def test_experiment_help_names_insights_writer(app) -> None:
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0, result.output
    help_text = " ".join(result.output.replace("│", " ").split())
    assert "nemo insights analyze" in help_text
    assert "writes by default" in help_text
