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
4. coverage    every task dir on disk against the set ``Job.create`` actually resolved,
               because Harbor drops one it cannot parse without raising.
5. credentials ``get_required_host_vars`` over the task and job env templates.
6. agent       ``import_class`` or ``AgentFactory.get_agent_class``, called the way Harbor's
               own ``AgentFactory`` calls them.
7. backend     ``EnvironmentFactory.run_preflight``.
8. round trip  ``harbor job start --print-config -c <file>`` against the persisted bytes.

Two findings are ours rather than Harbor's, and neither carries a ``harbor_call``. The reward
advisory reads the test scripts itself, because Harbor has no API that answers the question
before a trial runs, and it can only warn since a text search cannot tell a script that writes
a reward through a variable from one that never writes a reward at all. The agent base-class
advisory is a judgement Harbor deliberately does not make: it enforces a base for verifiers
and not for agents, so an agent that is a plain class is worth saying and not worth failing.

A failing rung is recorded, not raised. A report listing every problem is worth more than
one that stops at the first, and the command's whole job is to say why a repo cannot run.

Two side effects worth knowing. ``Job.create`` populates ``~/.cache/harbor`` when a config
names remote datasets, and rung 6 imports a module from the repo under test, which runs
that module's top level. Neither starts a container or writes into the repo.
"""

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
from nemo_eval_author_plugin.discovery.scan import display_path
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

    @property
    def runnable(self) -> bool:
        return self.config is not None and not any(item.status == "fail" for item in self.findings)


def _harbor(name: str, status: Status, message: str, call: str, **kwargs) -> Finding:
    """A finding Harbor returned, which is what ``harbor_call`` claims on the way out."""
    return Finding(
        name=name,
        group=_GROUP,
        status=status,
        message=message,
        harbor_call=call,
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
    _rung_agent(config, repo_root, candidate.agent_search_path, outcome)
    _rung_backend(config, outcome)
    if job is None:
        return outcome

    resolved = _resolved_local_paths(job)
    if resolved is None:
        # Not a `_harbor` finding: Harbor did not return this verdict, we reached for one of
        # its attributes and found it gone. Same shape as the round trip's "no harbor
        # executable on PATH" — the honest report is that Harbor could not be asked.
        outcome.findings.append(
            Finding(
                name="compatibility",
                group=_GROUP,
                status="fail",
                message="This Harbor version no longer exposes the resolved task list through Job._task_configs",
                hint=(
                    "Discovery reads the same private attribute Harbor's own CLI does, so this is an "
                    "incompatibility with the installed Harbor rather than a problem with this repo."
                ),
            )
        )
        return outcome

    task_dirs = _rung_tasks(resolved, outcome)
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


def _resolved_local_paths(job: Job) -> list[Path] | None:
    """The on-disk task directories Harbor expanded this job into, or ``None`` if it cannot say.

    Harbor's own CLI reaches for this attribute at harbor/cli/jobs.py:93 for the same
    reason; there is no public accessor for the resolved list. Tasks that live only in a
    remote registry are skipped, since the resolution rung already spoke for whether they
    could be fetched.

    A missing attribute is ``None`` rather than an empty list, because the two mean opposite
    things. Empty is a repo Harbor found no tasks in; absent is a Harbor that no longer
    answers the question, and collapsing them would report "the config resolves to zero
    tasks" about a repo whose tasks are fine.

    Absolute on the way out. Harbor hands back whatever the config said, and a relative path
    means the repo root only while the ladder's chdir is in effect, so the coverage rung
    would compare it against the wrong directory.
    """
    task_configs = getattr(job, "_task_configs", None)
    if task_configs is None:
        return None

    paths: list[Path] = []
    for task_config in task_configs:
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
    The tasks rung then reports seven of seven valid, the run scores seven, and nothing
    about the output looks incomplete. Without this rung the whole ladder returns a clean
    verdict on a suite that is quietly missing a third of itself.

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
    """Advisory: does each task's test script look like it writes a reward file?

    A task can be structurally valid and still score nothing, and Harbor only says so by
    raising ``RewardFileNotFoundError`` after a full trial. There is no Harbor API that
    answers earlier, so this reads the scripts and searches for a reward filename.

    That makes it a heuristic and it is reported as one: no ``harbor_call``, and never
    worse than a warning. A script that builds the path in a variable writes a reward this
    search cannot see, and failing the run over that would block a repo whose evals are
    fine.
    """
    silent: list[Path] = []
    reward_forms: set[str] = set()

    for task_dir in task_dirs:
        for script in _test_scripts(task_dir):
            text = _executable_lines(_read_text(script))
            found = [name for name in _REWARD_FILENAMES if name in text]
            if found:
                reward_forms.update(found)
            elif task_dir not in silent:
                silent.append(task_dir)

    if silent:
        outcome.findings.append(
            Finding(
                name="reward",
                group=_GROUP,
                status="warn",
                message=f"{len(silent)} task(s) have a test script that never names a reward file",
                path=silent[0],
                hint=(
                    "Harbor reads /logs/verifier/reward.json then reward.txt, and raises "
                    "RewardFileNotFoundError when neither exists. Read as text, so a script that "
                    "builds the path dynamically looks the same as one that writes nothing."
                ),
            )
        )
        return

    detail = ", ".join(sorted(reward_forms)) if reward_forms else "none read"
    outcome.findings.append(
        Finding(
            name="reward",
            group=_GROUP,
            status="pass",
            message=f"Every test script names a reward file ({detail})",
        )
    )


def _test_scripts(task_dir: Path) -> list[Path]:
    """Every host test script that has to produce a reward.

    Mirrors ``Task._validate_tests``: one script for a single-step task, and for a
    multi-step task the effective script per step, which is the step's own or the shared
    one it falls back to. Checking only the first would pass a task whose later step never
    scores, and that failure surfaces only after a full run.

    A step that grades from its own verifier image contributes no host script, which
    ``resolve_effective_verifier_env_config`` is what decides. Asking Harbor beats
    inferring it from a missing file, which cannot tell a task that grades from an image
    apart from one whose author forgot to write a test.
    """
    paths = TaskPaths(task_dir)
    config = _task_config(task_dir)
    if config is None:
        return []

    task_os = config.environment.os
    shared = paths.discovered_test_path_for(task_os)

    if not config.steps:
        if resolve_effective_verifier_env_config(config, step_cfg=None) is not None:
            return []
        return [shared] if shared is not None else []

    scripts: list[Path] = []
    for step in config.steps:
        if resolve_effective_verifier_env_config(config, step_cfg=step) is not None:
            continue
        effective = paths.discovered_step_test_path_for(step.name, task_os) or shared
        if effective is not None and effective not in scripts:
            scripts.append(effective)
    return scripts


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


def _rung_agent(config: JobConfig, repo_root: Path, search_path: str | None, outcome: ValidationOutcome) -> None:
    """Does the agent this config names actually exist?

    Importing the class proves what matters without constructing it. Harbor instantiates
    agents at trial time, but a discovery command has no business running a user's
    ``__init__``.
    """
    for agent in config.agents:
        if agent.import_path is not None:
            _check_agent_import(agent.import_path, repo_root, search_path, outcome)
        elif agent.name is not None:
            _check_agent_name(agent.name, outcome)


def _check_agent_import(import_path: str, repo_root: Path, search_path: str | None, outcome: ValidationOutcome) -> None:
    """Import the agent with the search path the persisted config will actually get.

    *search_path* is the single directory the artifact tells a run to put on ``PYTHONPATH``,
    or ``None`` when the config came with an import path we did not author. Arranging the
    import any other way — searching the repo for a file named after the module, say — passes
    this rung for a reason ``harbor job start -c`` will not have, which is how a config that
    cannot import its own agent came to be recorded as runnable.

    ``base`` is deliberately not passed. Harbor's ``AgentFactory`` calls
    ``import_class(import_path, label="agent")``, strict for verifiers and not for agents, and
    a rung stricter than the gate it stands for fails repos Harbor would run.
    """
    module_name = import_path.split(":", 1)[0]
    search_dir = None if search_path is None else (repo_root / search_path).resolve()
    with _module_search_path(search_dir, module_name):
        try:
            agent_class = import_class(import_path, label="agent")
        except Exception as exc:
            outcome.findings.append(
                _harbor(
                    "agent",
                    "fail",
                    f"Could not load agent {import_path}: {type(exc).__name__}: {exc}",
                    "import_class",
                    hint=_import_hint(repo_root, module_name, search_path),
                )
            )
            return
    outcome.findings.append(
        _harbor(
            "agent",
            "pass",
            f"Agent {import_path} imports as a class ({agent_class.__name__})"
            + (f", searching {search_path}" if search_path is not None else ""),
            "import_class",
        )
    )
    if not issubclass(agent_class, BaseAgent):
        outcome.findings.append(
            Finding(
                name="agent-base",
                group=_GROUP,
                status="warn",
                message=f"{import_path} does not subclass harbor.agents.base.BaseAgent",
                hint=(
                    "Harbor imports agents without checking a base class, so a run starts and "
                    "then fails at trial time on whichever method it expected."
                ),
            )
        )


def _import_hint(repo_root: Path, module_name: str, search_path: str | None) -> str:
    """Say what would make the import work, naming a directory holding the module if one does.

    The search is for the hint only. Letting it widen the path the rung imports from is the
    bug this whole function exists to explain.
    """
    top = module_name.split(".", 1)[0]
    found = [
        display_path(path.parent, repo_root)
        for path in sorted(repo_root.rglob(f"{top}.py"))
        if ".venv" not in path.parts and "site-packages" not in path.parts
    ]
    reason = (
        "Harbor imports the agent with plain importlib and never adds the working directory to sys.path."
        if search_path is None
        else f"PYTHONPATH={search_path} is what this config is recorded with, and {top} does not import from there."
    )
    remainder = [directory for directory in found if directory != search_path]
    if remainder:
        return f"{reason} {top}.py is at {remainder[0]}, so a run needs PYTHONPATH={remainder[0]} from the repo root."
    return reason


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
    harbor_bin = _harbor_executable()
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
def _module_search_path(directory: Path | None, module_name: str) -> Iterator[None]:
    """Put exactly *directory* on ``sys.path`` for the duration, then undo it.

    One directory, because that is what the artifact tells a run to export as ``PYTHONPATH``
    and the rung is only worth anything if it imports from the same place. ``None`` adds
    nothing, which is what a separate ``harbor`` process gets.

    The eviction is unconditional and matters more than the insertion. ``harbor_wrapper`` is a
    convention, so two different repos, or the same repo before and after an edit, claim the
    same module name. Without it the second import silently returns the first repo's module and
    the rung would validate a file that is not the one under inspection — and with nothing
    added to the path, a stale entry is the only way the import could succeed at all. Both
    changes are reversed on the way out, since this process did not ask to be reshaped.
    """
    top = module_name.split(".", 1)[0]
    entry = str(directory) if directory is not None and str(directory) not in sys.path else None
    if entry is not None:
        sys.path.insert(0, entry)
    displaced = sys.modules.pop(top, None)
    try:
        yield
    finally:
        if entry is not None:
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


def _harbor_executable() -> str | None:
    """The ``harbor`` console script from the same environment as the in-process Harbor.

    ``PATH`` is not good enough here. A ``uv tool`` or ``pipx`` install shadows the
    environment's own script, so a plain lookup can hand the round trip a different Harbor than
    every other rung used, while the report stamps only the in-process version. The script
    beside ``sys.executable`` is the one that imports the Harbor these verdicts came from.
    ``PATH`` remains the fallback, for an interpreter whose scripts live elsewhere.
    """
    beside = Path(sys.executable).parent / "harbor"
    if beside.is_file():
        return str(beside)
    return shutil.which("harbor")
