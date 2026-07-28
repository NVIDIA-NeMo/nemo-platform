# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist plugin CLI — ``nemo experimentalist ...`` subcommands."""

import asyncio
import os
import uuid
from collections.abc import MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urlsplit

import typer
import yaml
from nemo_experimentalist_plugin.client import make_client
from nemo_experimentalist_plugin.openshell.launcher import (
    OpenShellLaunchError,
    launch_in_openshell,
)
from nemo_experimentalist_plugin.preflight import (
    Probes,
    check_artifacts,
    check_datasets,
    check_environment,
    check_profile,
)
from nemo_experimentalist_plugin.profile import AgentProfile, load_profile
from nemo_experimentalist_plugin.resolve import (
    ResolveError,
    build_effective_experiment_plan,
    resolve_effective_insight,
    resolve_experiment_config,
    resolve_experiment_inputs,
)
from nemo_insights_plugin.contracts.checks import (
    CheckResult,
    advisories,
    format_report,
    required_failures,
)
from nemo_insights_plugin.contracts.profile import (
    EnvFileError,
    ProfileError,
    discover_profile,
    load_env_file,
    resolve_base_url,
)
from nemo_platform_plugin.cli import NemoCLI

DEFAULT_WORKSPACE = "default"
_CONTAINER_MARKER = Path("/etc/nemo-experimentalist-container")

_PREFLIGHT_PROBES: Probes | None = None  # test seam; None → real probes
_OPEN_SHELL_LAUNCHER = launch_in_openshell  # test seam
_CONTAINER_RUNTIME: bool | None = None  # test seam; None → inspect image marker

# Lazily imported in the experiment command: importing experimentalist.run reaches model
# construction that requires EXPERIMENTALIST_API_* env at import time, and this module
# must import env-less so `nemo experimentalist doctor` can diagnose the missing creds.
# Tests monkeypatch this global with a recorder, which bypasses the lazy import.
run_experimentalist = None

# TODO: Add remote train/validation dataset support when remote experiment mode is implemented.


def _inside_experimentalist_container() -> bool:
    return _CONTAINER_RUNTIME if _CONTAINER_RUNTIME is not None else _CONTAINER_MARKER.is_file()


def _sandbox_path(value: str | Path, *, workspace_dir: Path, option: str) -> str:
    """Translate an existing host path into the uploaded OpenShell workspace."""
    text = str(value)
    candidate = Path(text).expanduser()
    if not candidate.exists():
        return text

    resolved_workspace = workspace_dir.resolve()
    resolved_candidate = candidate.resolve()
    try:
        relative = resolved_candidate.relative_to(resolved_workspace)
    except ValueError as exc:
        raise OpenShellLaunchError(
            f"{option} resolves outside the OpenShell workspace {resolved_workspace}: {resolved_candidate}. "
            "Run from a directory that contains every local input."
        ) from exc
    return str(Path("/sandbox/project") / resolved_workspace.name / relative)


def _openshell_run_args(
    *,
    workspace_dir: Path,
    agent: str | None,
    agent_spec: str | None,
    insight: str | None,
    insight_id: str | None,
    no_insight: bool,
    profile_path: Path | None,
    train_dataset: str | None,
    validation_dataset: str | None,
    task_template: str | None,
    mode: Literal["local", "remote"],
    workspace: str | None,
    config: Path | None,
    framework_skills: list[Path],
) -> list[str]:
    args: list[str] = []
    path_options: tuple[tuple[str, str | Path | None], ...] = (
        ("--agent", agent),
        ("--agent-spec", agent_spec),
        ("--insight", insight),
        ("--profile", profile_path),
        ("--train-dataset", train_dataset),
        ("--validation-dataset", validation_dataset),
        ("--task-template", task_template),
        ("--config", config),
    )
    for option, value in path_options:
        if value is not None:
            args.extend([option, _sandbox_path(value, workspace_dir=workspace_dir, option=option)])
    if insight_id is not None:
        args.extend(["--insight-id", insight_id])
    if no_insight:
        args.append("--no-insight")
    args.extend(["--mode", mode])
    if workspace is not None:
        args.extend(["--workspace", workspace])
    for skills_dir in framework_skills:
        args.extend(
            [
                "--framework-skills",
                _sandbox_path(skills_dir, workspace_dir=workspace_dir, option="--framework-skills"),
            ]
        )
    return args


def _openshell_doctor_args(
    *,
    workspace_dir: Path,
    insight: str | None,
    insight_id: str | None,
    profile_path: Path | None,
) -> list[str]:
    args: list[str] = []
    if insight is not None:
        args.extend(["--insight", _sandbox_path(insight, workspace_dir=workspace_dir, option="--insight")])
    if insight_id is not None:
        args.extend(["--insight-id", insight_id])
    if profile_path is not None:
        args.extend(
            [
                "--profile",
                _sandbox_path(profile_path, workspace_dir=workspace_dir, option="--profile"),
            ]
        )
    return args


def _run_in_openshell(
    command: Literal["run", "doctor"],
    args: list[str],
    *,
    output_dir: Path | None,
    platform_url: str | None,
) -> None:
    exit_code = _OPEN_SHELL_LAUNCHER(
        command,
        args,
        workspace_dir=Path.cwd(),
        output_dir=output_dir,
        platform_url=platform_url,
    )
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def _default_experiment_dir(profile: AgentProfile | None) -> Path:
    if profile is None:
        experiments_root = Path("tmp")
    else:
        experiments_root = profile.profile_dir / ".nemo-optimizer" / "experiments"
    experiments_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    while True:
        candidate = experiments_root / f"{timestamp}-{uuid.uuid4().hex}"
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate


class ExperimentalistCLI(NemoCLI):
    """``nemo experimentalist ...`` subcommands."""

    name: ClassVar[str] = "experimentalist"
    description: ClassVar[str] = "NeMo Experimentalist commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch even when only one verb is registered."""

        @app.command("run")
        def run(
            agent: str | None = typer.Option(
                None,
                "--agent",
                help=(
                    "Baseline agent: a local directory or a git URL with an optional ref "
                    "(e.g. ssh://git@host/group/repo.git@main). Optional in Mode 1 (the insight "
                    "supplies the agent) and overrides the insight's agent when given. A git "
                    "source records provenance and enables --config storage.publish_winner to open a "
                    "draft PR/MR for the winner against that ref."
                ),
            ),
            agent_spec: str | None = typer.Option(
                None,
                "--agent-spec",
                help="URI of a markdown file describing the agent under test (its spec).",
            ),
            insight: str | None = typer.Option(
                None,
                "--insight",
                help=(
                    "Insight for Mode 1: a local insight file OR a platform insight id "
                    "(surfaced in Studio). A path that exists on disk is read locally; "
                    "otherwise it is fetched from the platform. Default: "
                    "<profile-dir>/.nemo-optimizer/insights.yaml when it exists (where "
                    "`nemo insights analyze` writes by default)."
                ),
            ),
            insight_id: str | None = typer.Option(
                None,
                "--insight-id",
                help=(
                    "Selector for a local multi-insight file: exact id/title first; "
                    "if none matches, a decimal value is a zero-based index."
                ),
            ),
            no_insight: bool = typer.Option(
                False,
                "--no-insight",
                help="Disable insight use (Mode 2), including the shared profile insight file.",
            ),
            profile_path: Path | None = typer.Option(
                None,
                "--profile",
                help="Path to optimizer.yaml. Default: discovered by walking up from the cwd.",
                exists=True,
                dir_okay=False,
                readable=True,
            ),
            train_dataset: str | None = typer.Option(
                None,
                "--train-dataset",
                help="Train dataset: local path or harbor registry ref. Falls back to the profile.",
            ),
            validation_dataset: str | None = typer.Option(
                None,
                "--validation-dataset",
                help="Validation dataset: local path or harbor registry ref. Falls back to the profile.",
            ),
            task_template: str | None = typer.Option(
                None,
                "--task-template",
                help="Evaluator-specific task-template URI. Required with --insight.",
            ),
            experiment_dir: Path | None = typer.Option(
                None,
                "--experiment-dir",
                "--output",
                "--experiments-output",
                "-o",
                help=(
                    "Host experiment directory. OpenShell downloads its artifacts here "
                    "(default: ./tmp/experimentalist-openshell)."
                ),
                file_okay=False,
                dir_okay=True,
            ),
            mode: Literal["local", "remote"] = typer.Option(
                "local",
                "--mode",
                help="Mode of the optimizer run.",
            ),
            workspace: str | None = typer.Option(
                None,
                "--workspace",
                help="Intake/NMP workspace for traces and run/candidate metadata. Falls back to the profile.",
            ),
            base_url: str | None = typer.Option(
                None,
                "--base-url",
                help=(
                    "Base URL of the running NMP instance. Default: NMP_BASE_URL "
                    "(shell or profile-dir .env), else http://localhost:8080."
                ),
                envvar="NMP_BASE_URL",
            ),
            config: Path | None = typer.Option(
                None,
                "--config",
                help="YAML or JSON configuration for the optimizer run.",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
            ),
            framework_skills: list[Path] = typer.Option(
                [],
                "--framework-skills",
                help="Path to a directory of framework skills to load into the optimizer agents. May be specified multiple times.",
                exists=True,
                file_okay=False,
                dir_okay=True,
                readable=True,
            ),
        ) -> None:
            """Run offline optimization for a baseline agent (local dir or git source)."""

            if no_insight and (insight is not None or insight_id is not None):
                typer.echo("--no-insight cannot be combined with --insight or --insight-id", err=True)
                raise typer.Exit(code=1)
            if mode == "remote":
                typer.echo("Remote mode is not implemented yet", err=True)
                raise typer.Exit(code=1)
            if not _inside_experimentalist_container():
                try:
                    forwarded_args = _openshell_run_args(
                        workspace_dir=Path.cwd(),
                        agent=agent,
                        agent_spec=agent_spec,
                        insight=insight,
                        insight_id=insight_id,
                        no_insight=no_insight,
                        profile_path=profile_path,
                        train_dataset=train_dataset,
                        validation_dataset=validation_dataset,
                        task_template=task_template,
                        mode=mode,
                        workspace=workspace,
                        config=config,
                        framework_skills=framework_skills,
                    )
                    _run_in_openshell(
                        "run",
                        forwarded_args,
                        output_dir=experiment_dir,
                        platform_url=base_url,
                    )
                except (OpenShellLaunchError, OSError) as exc:
                    typer.echo(str(exc), err=True)
                    raise typer.Exit(code=1) from None
                return

            async def _flow() -> str:
                """Resolve inputs (profile + flags) and run the Experimentalist."""
                profile, profile_load_error = _load_profile_or_error(profile_path)
                # Resolved AFTER the profile-dir .env load so an NMP_BASE_URL set there
                # takes effect; typer's envvar/flag binding (shell) wins.
                base_url_resolved = resolve_base_url(base_url)
                effective_insight = resolve_effective_insight(
                    profile=profile,
                    insight=insight,
                    insight_id=insight_id,
                    disabled=no_insight,
                )
                if no_insight:
                    typer.echo("Insight disabled: --no-insight (Mode 2)", err=True)
                elif effective_insight.is_profile_default:
                    # `nemo insights analyze` writes here by default: the verbs connect flag-free.
                    typer.echo(
                        f"Insight file: {effective_insight.ref} (default; pass --insight to override)",
                        err=True,
                    )
                _announce_credential_defaults()
                config_payload = _load_config_payload(config)
                effective_config = resolve_experiment_config(config_payload, profile)
                bridge_url = effective_config.evaluator.get("bridge_url")
                bridge_token_env = effective_config.evaluator.get(
                    "bridge_token_env",
                    "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
                )
                # Phase 1 — cheap environment checks BEFORE resolution: certain failures
                # (missing creds, docker down, harbor absent) surface as the grouped
                # report before any dataset download or the loop-chain import (which
                # itself requires EXPERIMENTALIST_API_* env) can preempt them. check_profile is
                # doctor-only on purpose: flags may fully specify the run, and resolution
                # reports missing inputs with the skeleton.
                _preflight_or_exit(
                    check_environment(
                        profile=profile,
                        insight=effective_insight.ref,
                        insight_id=effective_insight.selector,
                        base_url=base_url_resolved,
                        harbor_bridge_url=str(bridge_url) if bridge_url is not None else None,
                        harbor_bridge_token_env=str(bridge_token_env),
                        enforce_insight_agent=agent is None,
                        probes=_PREFLIGHT_PROBES,
                    )
                )
                try:
                    plan = build_effective_experiment_plan(
                        profile=profile,
                        agent=agent,
                        agent_spec=agent_spec,
                        insight=effective_insight.ref,
                        insight_id=effective_insight.selector,
                        no_insight=no_insight,
                        train_dataset=train_dataset,
                        validation_dataset=validation_dataset,
                        task_template=task_template,
                        workspace=workspace,
                        config_payload=config_payload,
                        framework_skills=framework_skills or None,
                    )
                except ResolveError as exc:
                    if profile_load_error is not None:
                        raise ResolveError(f"{profile_load_error}\n{exc}") from None
                    raise
                if profile_load_error is not None:
                    typer.echo(f"⚠ ignoring unusable optimizer.yaml: {profile_load_error}", err=True)
                # Phase 2 validates effective source/template/storage before
                # creating an output directory or downloading datasets.
                _preflight_or_exit(
                    check_artifacts(
                        profile,
                        task_template=plan.task_template,
                        agent_source=plan.agent,
                        storage=plan.config.storage.model_dump(),
                        require_template=plan.insight is not None,
                        probes=_PREFLIGHT_PROBES,
                    )
                )
                if experiment_dir is None:
                    experiment_dir_resolved = _default_experiment_dir(profile)
                    typer.echo(f"Experiment dir: {experiment_dir_resolved}", err=True)
                else:
                    experiment_dir_resolved = experiment_dir
                inputs = await resolve_experiment_inputs(
                    profile=profile,
                    scratch_dir=experiment_dir_resolved / "resolved",
                    plan=plan,
                )
                global run_experimentalist
                if run_experimentalist is None:
                    from nemo_experimentalist_plugin.experimentalist.run import (
                        run_experimentalist as _run_experimentalist,  # noqa: PLC0415
                    )

                    run_experimentalist = _run_experimentalist
                client = make_client(base_url_resolved)
                try:
                    return await run_experimentalist(
                        agent=inputs.agent,
                        agent_spec=inputs.agent_spec,
                        insight=inputs.insight,
                        train_dataset=inputs.train_dataset,
                        validation_dataset=inputs.validation_dataset,
                        task_template=inputs.task_template,
                        experiment_dir=experiment_dir_resolved,
                        workspace=inputs.workspace,
                        client=client,
                        config=inputs.config,
                        mode=mode,
                        framework_skills_dirs=inputs.framework_skills_dirs,
                    )
                finally:
                    await client.close()

            try:
                output_text = asyncio.run(_flow())
            except (OSError, ValueError, yaml.YAMLError) as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1) from None
            typer.echo(output_text)

        @app.command("doctor")
        def doctor(
            insight: str | None = typer.Option(None, "--insight", help="Optional insight ref to verify."),
            insight_id: str | None = typer.Option(
                None,
                "--insight-id",
                help="Select an exact id/title or zero-based index from a local multi-insight file.",
            ),
            profile_path: Path | None = typer.Option(None, "--profile", help="Path to optimizer.yaml."),
            base_url: str | None = typer.Option(
                None,
                "--base-url",
                help=(
                    "Base URL of the running NMP instance. Default: NMP_BASE_URL "
                    "(shell or profile-dir .env), else http://localhost:8080."
                ),
                envvar="NMP_BASE_URL",
            ),
        ) -> None:
            """Diagnose Experimentalist setup: profile, artifacts, credentials, platform, runtime."""
            if not _inside_experimentalist_container():
                try:
                    _run_in_openshell(
                        "doctor",
                        _openshell_doctor_args(
                            workspace_dir=Path.cwd(),
                            insight=insight,
                            insight_id=insight_id,
                            profile_path=profile_path,
                        ),
                        output_dir=None,
                        platform_url=base_url,
                    )
                except (OpenShellLaunchError, OSError) as exc:
                    typer.echo(str(exc), err=True)
                    raise typer.Exit(code=1) from None
                return
            found = profile_path or discover_profile()
            profile_obj, profile_error = None, None
            env_results: list[CheckResult] = []
            if found is not None:
                try:
                    profile_obj = load_profile(found)
                except ProfileError as exc:
                    profile_error = str(exc)
                try:
                    _announce_env_file(found.parent)
                except EnvFileError as exc:
                    env_results.append(
                        CheckResult(
                            name="profile-env",
                            group="profile",
                            status="fail",
                            severity="required",
                            message=str(exc),
                            hint="check that the file is readable UTF-8 text, or remove the broken .env file",
                        )
                    )
            base_url_resolved = resolve_base_url(base_url)
            _announce_credential_defaults()
            insight_results: list[CheckResult] = []
            try:
                effective_insight = resolve_effective_insight(
                    profile=profile_obj,
                    insight=insight,
                    insight_id=insight_id,
                )
            except ResolveError as exc:
                effective_insight = None
                insight_results.append(
                    CheckResult(
                        name="insight-resolution",
                        group="platform",
                        status="fail",
                        severity="required",
                        message=str(exc),
                    )
                )
            plan = None
            plan_results: list[CheckResult] = []
            if profile_obj is not None and effective_insight is not None:
                try:
                    plan = build_effective_experiment_plan(
                        profile=profile_obj,
                        insight=effective_insight.ref,
                        insight_id=effective_insight.selector,
                    )
                except ResolveError as exc:
                    plan_results.append(
                        CheckResult(
                            name="experiment-plan",
                            group="profile",
                            status="fail",
                            severity="required",
                            message=str(exc),
                            hint="fix optimizer.yaml or its referenced agent_spec/experiment_config",
                        )
                    )
            results = check_profile(profile_obj, profile_error) + env_results + plan_results + insight_results
            results += check_environment(
                profile=profile_obj,
                insight=effective_insight.ref if effective_insight is not None else None,
                insight_id=effective_insight.selector if effective_insight is not None else None,
                base_url=base_url_resolved,
                harbor_bridge_url=(
                    str(plan.config.evaluator.get("bridge_url"))
                    if plan is not None and plan.config.evaluator.get("bridge_url") is not None
                    else None
                ),
                harbor_bridge_token_env=(
                    str(
                        plan.config.evaluator.get(
                            "bridge_token_env",
                            "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN",
                        )
                    )
                    if plan is not None
                    else "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
                ),
                probes=_PREFLIGHT_PROBES,
            )
            if profile_obj is not None:
                if plan is not None:
                    results += check_artifacts(
                        profile_obj,
                        task_template=plan.task_template,
                        agent_source=plan.agent,
                        storage=plan.config.storage.model_dump(),
                        require_template=plan.insight is not None,
                        probes=_PREFLIGHT_PROBES,
                    )
                results += check_datasets(profile_obj)
            typer.echo(format_report(results))
            if required_failures(results):
                raise typer.Exit(code=1)

        return app


def _load_profile_or_error(profile_path: Path | None) -> tuple[AgentProfile | None, str | None]:
    """Load the explicit or discovered profile; announce a discovered one.

    An explicitly named ``--profile`` must load (ProfileError propagates). A
    discovered optimizer.yaml that fails to load is returned as an error
    string — it may be a malformed or foreign file, and flags can still fully
    specify the run. A successfully discovered profile is echoed to stderr so
    a stray parent-directory optimizer.yaml can never silently govern a run.
    """
    found = profile_path or discover_profile()
    if found is None:
        return None, None
    try:
        profile = load_profile(found)
    except ProfileError as exc:
        if profile_path is not None:
            raise
        _announce_env_file(found.parent)
        return None, str(exc)
    if profile_path is None:
        typer.echo(f"Using profile: {found} (agent: {profile.agent})", err=True)
    _announce_env_file(found.parent)
    return profile, None


def _announce_env_file(profile_dir: Path) -> None:
    """Load ``<profile_dir>/.env`` into the process env (set keys win) and say so."""
    env_path = profile_dir / ".env"
    loaded = load_env_file(env_path)
    if loaded:
        typer.echo(f"Loaded .env from {env_path} ({len(loaded)} vars)", err=True)


_GATEWAY_BASE = "https://inference-api.nvidia.com/v1"
_GATEWAY_HOST = "inference-api.nvidia.com"


def _is_gateway_base(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == _GATEWAY_HOST


def _apply_credential_defaults(env: MutableMapping[str, str] = os.environ) -> list[str]:
    """Fill gateway-shaped credential gaps; returns what was applied.

    ``EXPERIMENTALIST_API_BASE`` defaults to the NVIDIA Inference Gateway, and when
    the effective base IS the gateway, ``INFERENCE_API_KEY`` can power the
    experimentalist too. A custom base never inherits the gateway key.
    """
    applied: list[str] = []
    if not env.get("EXPERIMENTALIST_API_BASE", "").strip():
        env["EXPERIMENTALIST_API_BASE"] = _GATEWAY_BASE
        applied.append(f"EXPERIMENTALIST_API_BASE={_GATEWAY_BASE}")
    if _is_gateway_base(env["EXPERIMENTALIST_API_BASE"]):
        inference = env.get("INFERENCE_API_KEY", "").strip()
        optimizer = env.get("EXPERIMENTALIST_API_KEY", "").strip()
        if inference and not optimizer:
            env["EXPERIMENTALIST_API_KEY"] = inference
            applied.append("EXPERIMENTALIST_API_KEY=INFERENCE_API_KEY")
    return applied


def _announce_credential_defaults() -> None:
    applied = _apply_credential_defaults()
    if applied:
        typer.echo("Credential defaults: " + ", ".join(applied), err=True)


def _load_config_payload(config: Path | None) -> dict | None:
    """Read a --config file; an explicitly passed empty file is an error, not
    a silent fallback to the profile's experiment_config."""
    if config is None:
        return None
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"--config {config} is empty; remove the flag or add settings to the file")
    return payload


def _preflight_or_exit(results: list[CheckResult]) -> None:
    """Auto-run gate: hard-error on required failures, warn on advisories."""
    if required_failures(results):
        typer.echo(format_report(results), err=True)
        raise typer.Exit(code=1)
    for warning in advisories(results):
        typer.echo(f"⚠ {warning.message}" + (f" ({warning.hint})" if warning.hint else ""), err=True)
