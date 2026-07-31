# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prove a candidate job config runnable using Harbor's own validators.

Every rung here is a Harbor call. That is the entire point: a later agent is meant to run
what discover recorded without re-deriving it, which is only safe if the verdicts came
from the same code the run will use. Reimplementing Harbor's rules would produce a report
that agrees with Harbor today and drifts silently tomorrow.

The rungs, in order, and the Harbor API each one leans on:

1. schema      ``JobConfig.model_validate`` plus ``validate_agent_concurrency_limits``,
               which is what ``harbor job start --print-config`` runs before it returns.
2. resolution  ``Job.create``, which resolves skills, task configs, resource policies and
               metrics, and starts no container.
3. tasks       ``Task.is_valid_dir``, then ``Task()`` to get the reason a task failed.
4. reward      the resolved test script must write ``/logs/verifier/reward.{json,txt}``.
5. credentials ``get_required_host_vars`` over the task and job env templates.
6. agent       ``import_class(..., base=BaseAgent)`` or ``AgentFactory.get_agent_class``.
7. backend     ``EnvironmentFactory.run_preflight``.
8. round trip  ``harbor job start --print-config -c <file>`` against the persisted bytes.

A failing rung is recorded, not raised. A report listing every problem is worth more than
one that stops at the first, and the command's whole job is to say why a repo cannot run.

Two side effects worth knowing. ``Job.create`` populates ``~/.cache/harbor`` when a config
names remote datasets, and rung 6 imports a module from the repo under test, which runs
that module's top level. Neither starts a container or writes into the repo.
"""

import asyncio
import contextlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.agents.factory import AgentFactory
from harbor.environments.factory import EnvironmentFactory
from harbor.job import Job
from harbor.models.agent.name import AgentName
from harbor.models.job.config import JobConfig
from harbor.models.task.config import TaskConfig as TaskDefinitionConfig
from harbor.models.task.paths import TaskPaths
from harbor.models.task.task import Task
from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config
from harbor.utils.env import get_required_host_vars
from harbor.utils.import_path import import_class
from nemo_eval_author_plugin.discovery.models import CandidateConfig, Finding, RequiredEnvVar, Status
from pydantic import ValidationError

_GROUP = "validation"

# Harbor reads reward.json first and falls back to reward.txt; a test script naming
# neither fails the trial with RewardFileNotFoundError no matter how good the agent is.
_REWARD_FILENAMES = ("reward.json", "reward.txt")

_TASK_CONFIG_FILENAME = "task.toml"
# Harbor skips a dataset child named task_template; it is a scaffold, not a task.
_TEMPLATE_DIR_NAME = "task_template"
_MAX_LISTED_DROPPED = 5

_PRINT_CONFIG_TIMEOUT_SEC = 120.0


@dataclass
class ValidationOutcome:
    """What the ladder concluded, and the evidence it gathered on the way."""

    config: JobConfig | None = None
    findings: list[Finding] = field(default_factory=list)
    required_env_vars: list[RequiredEnvVar] = field(default_factory=list)
    task_dirs: list[Path] = field(default_factory=list)

    @property
    def runnable(self) -> bool:
        return self.config is not None and not any(item.status == "fail" for item in self.findings)


def _harbor(name: str, status: Status, message: str, call: str, **kwargs) -> Finding:
    """A finding Harbor vouches for, which is the only kind this module emits."""
    return Finding(
        name=name,
        group=_GROUP,
        status=status,
        message=message,
        harbor_call=call,
        provenance="harbor",
        **kwargs,
    )


async def run_ladder(candidate: CandidateConfig, repo_root: Path) -> ValidationOutcome:
    """Judge the config from the directory a real run would be started in.

    Harbor resolves a config's relative paths against the process directory, and a config a
    repo maintains says ``path: evals/validation`` meaning "from the repo root". Validating
    it from anywhere else reports a dataset Harbor cannot find while ``harbor job start -c``
    from the repo root would run it — a false verdict on the case that matters most. The
    subprocess round trip already passes ``cwd``; this gives the in-process rungs the same
    footing. A process-wide chdir is only defensible because the CLI awaits one ladder and
    nothing else.
    """
    with contextlib.chdir(repo_root):
        return await _ladder(candidate, repo_root)


async def _ladder(candidate: CandidateConfig, repo_root: Path) -> ValidationOutcome:
    """Walk the ladder, stopping only where a later rung has nothing left to judge."""
    outcome = ValidationOutcome()

    config = _rung_schema(candidate, outcome)
    if config is None:
        return outcome
    outcome.config = config

    job = await _rung_resolution(config, outcome)
    _rung_agent(config, repo_root, outcome)
    _rung_backend(config, outcome)
    if job is None:
        return outcome

    resolved = _resolved_local_paths(job)
    task_dirs = _rung_tasks(resolved, outcome)
    outcome.task_dirs = task_dirs
    _rung_coverage(config, resolved, outcome)
    if not task_dirs:
        return outcome

    _rung_reward(task_dirs, outcome)
    _rung_credentials(config, task_dirs, outcome)
    return outcome


def _rung_schema(candidate: CandidateConfig, outcome: ValidationOutcome) -> JobConfig | None:
    """Does the payload satisfy Harbor's job config schema?"""
    try:
        config = JobConfig.model_validate(candidate.data)
        # Redundant with the model's own after-validator, and kept because it is the gate
        # the CLI runs by hand at harbor/cli/jobs.py:1473 after it applies flags. If we
        # ever mutate a config post-validation, this is the line that catches it.
        config.validate_agent_concurrency_limits()
    except ValidationError as exc:
        details = "; ".join(error["msg"] for error in exc.errors(include_url=False, include_input=False))
        outcome.findings.append(
            _harbor(
                "schema",
                "fail",
                f"Job config does not satisfy Harbor's schema: {details}",
                "JobConfig.model_validate",
                path=candidate.source.path,
                hint=f"Assembled from the {candidate.source.kind} source ({candidate.source.detail}).",
            )
        )
        return None
    except ValueError as exc:
        outcome.findings.append(
            _harbor(
                "schema",
                "fail",
                f"Job config is internally inconsistent: {exc}",
                "JobConfig.validate_agent_concurrency_limits",
                path=candidate.source.path,
            )
        )
        return None

    outcome.findings.append(
        _harbor(
            "schema",
            "pass",
            "Harbor accepts the job config schema",
            "JobConfig.model_validate",
            path=candidate.source.path,
        )
    )
    return config


async def _rung_resolution(config: JobConfig, outcome: ValidationOutcome) -> Job | None:
    """Can Harbor resolve every dataset, skill and metric the config names?

    ``Job.create`` is the deepest gate available without running anything: it expands
    datasets into task configs, resolves skill sources, validates resource policies
    against the chosen backend, and builds metrics. Anything it raises is an error the
    real run would have hit at the same point.

    It does have one side effect: it opens its output directory and starts a ``job.log``
    there. ``jobs_dir`` defaults to a relative ``jobs/``, which the ladder's chdir would put
    inside the repo, so resolution runs against a copy pointed at scratch space. A copy
    because the original is what gets persisted, and a real run's output belongs wherever
    that run decides, not in a temp dir that no longer exists.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="eval-author-jobs-") as scratch:
            job = await Job.create(config.model_copy(update={"jobs_dir": Path(scratch)}))
    except Exception as exc:
        outcome.findings.append(
            _harbor(
                "resolution",
                "fail",
                f"Harbor could not resolve the job: {type(exc).__name__}: {exc}",
                "Job.create",
                hint="This is the error a real run would raise before starting any container.",
            )
        )
        return None

    outcome.findings.append(
        _harbor(
            "resolution",
            "pass",
            "Harbor resolved datasets, skills, metrics and resource policies",
            "Job.create",
        )
    )
    return job


def _resolved_local_paths(job: Job) -> list[Path]:
    """The on-disk task directories Harbor expanded this job into.

    Harbor's own CLI reaches for this attribute at harbor/cli/jobs.py:93 for the same
    reason; there is no public accessor for the resolved list. Tasks that live only in a
    remote registry are skipped, since the resolution rung already spoke for whether they
    could be fetched.

    Absolute on the way out. Harbor hands back whatever the config said, and a relative path
    means the repo root only while the ladder's chdir is in effect; these outlive it as the
    task list the report fingerprints.
    """
    paths: list[Path] = []
    for task_config in getattr(job, "_task_configs", []):
        try:
            paths.append(task_config.get_local_path().resolve())
        except ValueError:
            continue
    return paths


def _rung_tasks(resolved: list[Path], outcome: ValidationOutcome) -> list[Path]:
    """Is each resolved task a valid Harbor task directory?

    Deferring to ``Task.is_valid_dir`` rather than checking for ``tests/`` and
    ``environment/`` by hand is what keeps this from crying wolf on the four shapes a
    naive check gets wrong: a multi-step task whose instruction lives under ``steps/``, a
    Windows task carrying ``test.bat``, a task whose verifier bakes its tests into a
    separate image, and a task with ``[environment].docker_image`` and no Dockerfile.
    """
    valid: list[Path] = []
    invalid: list[tuple[Path, str]] = []
    for local_path in resolved:
        if Task.is_valid_dir(local_path):
            valid.append(local_path)
        else:
            invalid.append((local_path, _task_failure_reason(local_path)))

    if not resolved:
        outcome.findings.append(
            _harbor(
                "tasks",
                "fail",
                "The config resolves to zero tasks",
                "Job.create",
                hint="Harbor raises 'Either datasets or tasks must be provided' for an empty task set.",
            )
        )
        return []

    status = "fail" if invalid else "pass"
    outcome.findings.append(
        _harbor(
            "tasks",
            status,
            f"{len(valid)} of {len(valid) + len(invalid)} task dirs are valid Harbor tasks",
            "Task.is_valid_dir",
        )
    )
    for path, reason in invalid:
        outcome.findings.append(_harbor("tasks", "fail", f"{path.name}: {reason}", "Task.is_valid_dir", path=path))
    return valid


def _rung_coverage(config: JobConfig, resolved: list[Path], outcome: ValidationOutcome) -> None:
    """Did Harbor pick up every task the repo appears to contain?

    Harbor drops a directory it cannot parse as a task without saying so: given ten task
    dirs where three are half-written, ``Job.create`` resolves seven and raises nothing.
    The run then succeeds and reports a score over seven tasks, which is the most expensive
    kind of wrong, because nothing about the output looks incomplete.

    A dataset that narrows itself with ``task_names``, ``exclude_task_names`` or ``n_tasks``
    is deliberately running a subset, so its unresolved directories are reported as
    information rather than as a problem.
    """
    resolved_set = {path.resolve() for path in resolved}
    for dataset in config.datasets:
        if dataset.path is None or not dataset.path.is_dir():
            continue
        on_disk = [
            child
            for child in sorted(dataset.path.iterdir())
            if child.is_dir() and (child / _TASK_CONFIG_FILENAME).is_file() and child.name != _TEMPLATE_DIR_NAME
        ]
        dropped = [child for child in on_disk if child.resolve() not in resolved_set]
        if not dropped:
            continue

        selective = dataset.task_names or dataset.exclude_task_names or dataset.n_tasks
        listed = ", ".join(f"{child.name} ({_task_failure_reason(child)})" for child in dropped[:_MAX_LISTED_DROPPED])
        remainder = len(dropped) - _MAX_LISTED_DROPPED
        message = f"{len(dropped)} of {len(on_disk)} task dir(s) under {dataset.path.name} were not picked up: {listed}"
        outcome.findings.append(
            _harbor(
                "coverage",
                "warn" if selective else "fail",
                message + (f", and {remainder} more" if remainder > 0 else ""),
                "Job.create",
                path=dataset.path,
                hint=(
                    "The dataset selects a subset, so this is expected."
                    if selective
                    else "Harbor skips these silently, so a run would score fewer tasks than the repo contains."
                ),
            )
        )


def _task_failure_reason(task_dir: Path) -> str:
    """Ask Harbor why a task is invalid, since ``is_valid_dir`` only says that it is."""
    try:
        Task(task_dir)
    except FileNotFoundError as exc:
        return str(exc)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        return f"task.toml could not be read: {exc}"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return "rejected by Task.is_valid_dir"


def _rung_reward(task_dirs: list[Path], outcome: ValidationOutcome) -> None:
    """Does each task's test script actually write a reward file?

    A task can be structurally valid and still score nothing, which is the most
    expensive way to discover a problem: the trial runs, the agent works, and Harbor
    raises ``RewardFileNotFoundError`` at the end.
    """
    missing: list[Path] = []
    image_provided: list[Path] = []
    reward_forms: set[str] = set()

    for task_dir in task_dirs:
        scripts, graded_in_image = _test_scripts(task_dir)
        if graded_in_image:
            image_provided.append(task_dir)
        for script in scripts:
            text = _executable_lines(_read_text(script))
            found = [name for name in _REWARD_FILENAMES if name in text]
            if found:
                reward_forms.update(found)
            elif task_dir not in missing:
                missing.append(task_dir)

    if missing:
        outcome.findings.append(
            _harbor(
                "reward",
                "fail",
                f"{len(missing)} task(s) have a test script that never writes a reward file",
                "TaskPaths.discovered_test_path_for",
                path=missing[0],
                hint=(
                    "Harbor reads /logs/verifier/reward.json then reward.txt, and raises "
                    "RewardFileNotFoundError when neither exists."
                ),
            )
        )
        return

    detail = ", ".join(sorted(reward_forms)) if reward_forms else "none read"
    message = f"Every test script writes a reward file ({detail})"
    if image_provided:
        message += f"; {len(image_provided)} task(s) grade from a separate verifier image"
    outcome.findings.append(
        _harbor(
            "reward",
            "pass",
            message,
            "TaskPaths.discovered_test_path_for",
            hint=(
                "reward.txt yields the single key 'reward'; reward.json keys are only "
                "known once a trial runs, and they decide what metrics can aggregate."
            ),
        )
    )


def _test_scripts(task_dir: Path) -> tuple[list[Path], bool]:
    """Every host test script that has to produce a reward, and whether any grades in-image.

    Mirrors ``Task._validate_tests``: one script for a single-step task, and for a
    multi-step task the effective script per step, which is the step's own or the shared
    one it falls back to. Checking only the first would pass a task whose later step never
    scores, and that failure surfaces only after a full run.

    ``resolve_effective_verifier_env_config`` is what decides the in-image case. Asking
    Harbor beats inferring it from a missing file, which cannot tell a task that grades
    from its own verifier image apart from one whose author forgot to write a test.
    """
    paths = TaskPaths(task_dir)
    config = _task_config(task_dir)
    if config is None:
        return [], False

    task_os = config.environment.os
    shared = paths.discovered_test_path_for(task_os)

    if not config.steps:
        if resolve_effective_verifier_env_config(config, step_cfg=None) is not None:
            return [], True
        return ([shared] if shared is not None else []), False

    scripts: list[Path] = []
    graded_in_image = False
    for step in config.steps:
        if resolve_effective_verifier_env_config(config, step_cfg=step) is not None:
            graded_in_image = True
            continue
        effective = paths.discovered_step_test_path_for(step.name, task_os) or shared
        if effective is not None and effective not in scripts:
            scripts.append(effective)
    return scripts, graded_in_image


def _rung_credentials(config: JobConfig, task_dirs: list[Path], outcome: ValidationOutcome) -> None:
    """Which host variables must be set for this config to run?

    Harbor resolves ``${VAR}`` and ``${VAR:-default}`` templates from the host
    environment at run time and raises on a missing one, and ``harbor run`` stops to ask
    the user before handing any of them to a container. Discover records the names so the
    persisted artifact is honest about what a run needs. Whether this machine has values
    for them is ``doctor``'s question.
    """
    required: dict[str, RequiredEnvVar] = {}

    def collect(env: dict[str, str], declared_in: Path) -> None:
        for name, default in get_required_host_vars(env):
            required.setdefault(name, RequiredEnvVar(name=name, default=default, declared_in=declared_in))

    for task_dir in task_dirs:
        task_config = _task_config(task_dir)
        if task_config is None:
            continue
        config_path = TaskPaths(task_dir).config_path
        collect(task_config.environment.env, config_path)
        collect(task_config.verifier.env, config_path)
        collect(task_config.solution.env, config_path)

    job_level = Path("<job config>")
    collect(config.environment.env, job_level)
    collect(config.verifier.env, job_level)
    for agent in config.agents:
        collect(agent.env, job_level)

    outcome.required_env_vars = sorted(required.values(), key=lambda item: item.name)
    names = ", ".join(item.name for item in outcome.required_env_vars)
    outcome.findings.append(
        _harbor(
            "credentials",
            "pass",
            f"{len(outcome.required_env_vars)} host variable(s) required" + (f": {names}" if names else ""),
            "get_required_host_vars",
            hint="Set these before running; Harbor raises on a missing template at trial start." if names else None,
        )
    )


def _rung_agent(config: JobConfig, repo_root: Path, outcome: ValidationOutcome) -> None:
    """Does the agent this config names actually exist?

    Importing the class proves what matters without constructing it. Harbor instantiates
    agents at trial time, but a discovery command has no business running a user's
    ``__init__``, and ``import_class`` already enforces the ``BaseAgent`` contract.
    """
    for agent in config.agents:
        if agent.import_path is not None:
            _check_agent_import(agent.import_path, repo_root, outcome)
        elif agent.name is not None:
            _check_agent_name(agent.name, outcome)


def _check_agent_import(import_path: str, repo_root: Path, outcome: ValidationOutcome) -> None:
    module_name = import_path.split(":", 1)[0]
    with _module_search_path(repo_root, module_name):
        try:
            agent_class = import_class(import_path, base=BaseAgent, label="agent")
        except Exception as exc:
            outcome.findings.append(
                _harbor(
                    "agent",
                    "fail",
                    f"Could not load agent {import_path}: {type(exc).__name__}: {exc}",
                    "import_class",
                    hint="Harbor needs the module importable and the class to subclass BaseAgent.",
                )
            )
            return
    outcome.findings.append(
        _harbor(
            "agent",
            "pass",
            f"Agent {import_path} imports and subclasses BaseAgent ({agent_class.__name__})",
            "import_class",
        )
    )


def _check_agent_name(name: str, outcome: ValidationOutcome) -> None:
    if name not in AgentName.values():
        outcome.findings.append(
            _harbor(
                "agent",
                "fail",
                f"'{name}' is not a Harbor agent name",
                "AgentName.values",
                hint=f"Valid names: {', '.join(sorted(AgentName.values()))}",
            )
        )
        return
    try:
        AgentFactory.get_agent_class(AgentName(name))
    except Exception as exc:
        outcome.findings.append(
            _harbor(
                "agent",
                "fail",
                f"Harbor knows agent '{name}' but cannot import it: {type(exc).__name__}: {exc}",
                "AgentFactory.get_agent_class",
                hint="Built-in agents can need an optional extra, as in `pip install 'harbor[...]'`.",
            )
        )
        return
    outcome.findings.append(
        _harbor("agent", "pass", f"Built-in agent '{name}' is available", "AgentFactory.get_agent_class")
    )


def _rung_backend(config: JobConfig, outcome: ValidationOutcome) -> None:
    """Is the environment backend usable here?

    Harbor's own preflight is the check. For docker that means the binary is on PATH and
    the daemon answers, and it reports the problem by raising ``SystemExit``, which is
    fine for a CLI and has to be caught here.
    """
    label = config.environment.import_path or (
        config.environment.type.value if config.environment.type is not None else "docker"
    )
    try:
        EnvironmentFactory.run_preflight(config.environment.type, config.environment.import_path)
    except SystemExit as exc:
        outcome.findings.append(
            _harbor(
                "backend",
                "fail",
                f"Environment backend '{label}' is not ready: {exc}",
                "EnvironmentFactory.run_preflight",
            )
        )
        return
    except Exception as exc:
        outcome.findings.append(
            _harbor(
                "backend",
                "fail",
                f"Environment backend '{label}' preflight failed: {type(exc).__name__}: {exc}",
                "EnvironmentFactory.run_preflight",
                hint="Cloud backends need their optional extra installed and vendor credentials set.",
            )
        )
        return
    outcome.findings.append(
        _harbor(
            "backend", "pass", f"Environment backend '{label}' passed preflight", "EnvironmentFactory.run_preflight"
        )
    )


def check_config_file(config_path: Path, repo_root: Path) -> Finding:
    """Load the file a later run will pass to ``-c`` through the Harbor CLI itself.

    The only rung that judges bytes rather than an in-memory object, which matters
    because bytes are what a later agent will hand to Harbor. ``--print-config`` returns
    before ``Job.create``, so this re-validates the schema and resolves nothing. It runs
    with ``cwd`` at the repo root because these configs use repo-relative paths.

    The file is either one discovery wrote or the repo's own, whichever the artifact ends
    up pointing at; the check is the same either way.
    """
    harbor_bin = shutil.which("harbor")
    if harbor_bin is None:
        return Finding(
            name="round-trip",
            group=_GROUP,
            status="warn",
            message="Skipped the CLI round trip: no `harbor` executable on PATH",
            hint="The in-process schema rung already accepted this config.",
        )

    try:
        completed = subprocess.run(
            [harbor_bin, "job", "start", "--print-config", "-c", str(config_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_PRINT_CONFIG_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Finding(
            name="round-trip",
            group=_GROUP,
            status="warn",
            message=f"Could not run the CLI round trip: {type(exc).__name__}: {exc}",
            path=config_path,
        )

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return _harbor(
            "round-trip",
            "fail",
            f"`harbor job start --print-config` rejected the config file: {detail[-1] if detail else 'no output'}",
            "harbor job start --print-config",
            path=config_path,
        )
    return _harbor(
        "round-trip",
        "pass",
        "The config file loads through the Harbor CLI",
        "harbor job start --print-config",
        path=config_path,
    )


@contextlib.contextmanager
def _module_search_path(repo_root: Path, module_name: str) -> Iterator[None]:
    """Make *module_name* importable from this repo, then undo it.

    Two things have to be arranged. A wrapper is referenced as
    ``harbor_wrapper:WrappedAgent``, a bare module name that only imports if its directory
    is on ``sys.path``; Harbor's callers arrange that themselves at run time.

    And the name has to be evicted from ``sys.modules`` first. ``harbor_wrapper`` is a
    convention, so two different repos, or the same repo before and after an edit, claim the
    same module name. Without eviction the second import silently returns the first repo's
    module and the rung would validate a file that is not the one under inspection. Both
    changes are reversed on the way out, since this process did not ask to be reshaped.
    """
    top = module_name.split(".", 1)[0]
    directories = [
        path.parent
        for path in sorted(repo_root.rglob(f"{top}.py"))
        if ".venv" not in path.parts and "site-packages" not in path.parts
    ]
    added = [str(directory) for directory in directories if str(directory) not in sys.path]
    sys.path[:0] = added
    displaced = sys.modules.pop(top, None)
    try:
        yield
    finally:
        for entry in added:
            with contextlib.suppress(ValueError):
                sys.path.remove(entry)
        sys.modules.pop(top, None)
        if displaced is not None:
            sys.modules[top] = displaced


def _task_config(task_dir: Path) -> TaskDefinitionConfig | None:
    try:
        return TaskDefinitionConfig.model_validate_toml(TaskPaths(task_dir).config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValidationError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _executable_lines(text: str) -> str:
    """Drop comment lines before looking for a reward file.

    Harbor's own task template ships a ``test.sh`` that writes nothing and only mentions
    ``reward.txt`` in a comment telling the author to write one. Grepping raw text would
    pass exactly the task most likely to be broken: a scaffold nobody finished.
    """
    kept = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("#", "::")) and not line.lstrip().upper().startswith("REM ")
    ]
    return "\n".join(kept)


def validate(candidate: CandidateConfig, repo_root: Path) -> ValidationOutcome:
    """Synchronous entry point, since the CLI is not async but ``Job.create`` is."""
    return asyncio.run(run_ladder(candidate, repo_root))


def temp_logs_dir() -> tempfile.TemporaryDirectory:
    """Exposed for tests that need a throwaway logs dir when constructing agents."""
    return tempfile.TemporaryDirectory(prefix="eval-author-discover-")
