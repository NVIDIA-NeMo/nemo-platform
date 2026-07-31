# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assemble a candidate Harbor job config from whatever the repo already declares.

Four sources, ranked in ``SOURCE_PRIORITY`` by how much of the config Harbor has already
agreed to. A config file the user wrote beats a config Harbor once ran, which beats one
we assembled from ``optimizer.yaml``, which beats one inferred from directory names.

Nothing in this module validates anything. Every source hands back a raw mapping and a
note about where it came from, and the ladder in ``validate`` owns every verdict. Keeping
assembly apart from judgement is what turns "no config reaches the artifact unless Harbor
accepted it" into a property that can be checked rather than a promise: if this module
returned a parsed ``JobConfig``, the schema rung would already have run off to the side.

Paths inside the config come back absolute so validation needs no working-directory tricks.
Rewriting them relative to the repo for the persisted artifact is ``report``'s job. The one
exception is ``CandidateConfig.agent_search_path``, which is repo-relative from the start
because it is not a config field: it is the ``PYTHONPATH`` a run needs, and both the ladder
and the artifact read it as written.
"""

import ast
import json
from pathlib import Path
from typing import Any, Literal, NamedTuple

import yaml
from nemo_eval_author_plugin.discovery.models import (
    CandidateConfig,
    ConfigSource,
    Finding,
)
from nemo_eval_author_plugin.discovery.scan import display_path, walk_dirs
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import _AGENT_IMPORT_ROOT
from nemo_insights_plugin.contracts.profile import (
    PROFILE_FILENAME,
    ProfileError,
    discover_profile,
    load_profile_model,
    resolve_profile_path,
)
from pydantic import BaseModel, ConfigDict, Field

_GROUP = "config"

DatasetKind = Literal["path", "ref"]

# `harbor job init` writes into `configs/` unless told otherwise, so look there first.
_CONFIG_SEARCH_DIRS = ("configs", ".", "harbor", ".harbor", "evals")
_CONFIG_SUFFIXES = (".yaml", ".yml", ".json")

_TASK_CONFIG_FILENAME = "task.toml"
_TEMPLATE_DIR_NAME = "task_template"
_WRAPPER_FILENAME = "harbor_wrapper.py"
_AGENT_BASE_CLASSES = frozenset({"BaseAgent", "BaseInstalledAgent"})
_CONVENTIONAL_DATASET_DIRS = ("evals/validation", "evals/val", "evals/train")


class _ProfileDatasets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    train: str | None = None
    validation: str | None = None
    registry_url: str | None = None
    """Present or absent, this decides how the split values are read, so it cannot be ignored.

    ``extra="ignore"`` swallowed it before, which left every value looking like a local path
    and turned ``validation: tau2-bench-live-validation@1.0`` into a directory that is not
    there.
    """


class _DiscoveryProfile(BaseModel):
    """The ``optimizer.yaml`` fields discover needs, and nothing else.

    Lenient where Experimentalist's ``AgentProfile`` is strict. That model forbids extras
    and lives behind the import boundary, so a repo written for a newer Experimentalist
    would make discover fail on a key it does not even read. Ignoring extras is the point.
    """

    model_config = ConfigDict(extra="ignore")

    agent: str | None = None
    task_template: str | None = None
    agent_source: str = "."
    datasets: _ProfileDatasets = Field(default_factory=_ProfileDatasets)
    profile_dir: Path


def find_candidate(repo_root: Path) -> tuple[CandidateConfig | None, list[Finding]]:
    """Return the highest-priority candidate config found in *repo_root*.

    Every source is attempted even once one has won, because "we also found a prior job
    directory" is worth saying: it tells a reader which evidence was passed over.
    """
    # Resolved once here so every path downstream is comparable. The walk resolves as it
    # goes, and on macOS a caller's /tmp is the walk's /private/tmp, which would make
    # rendering a path relative to the repo fail on a symlinked root.
    repo_root = repo_root.resolve()
    findings: list[Finding] = []
    candidates: list[CandidateConfig] = []

    for source in (_from_config_file, _from_prior_job, _from_profile, _from_convention):
        candidate, source_findings = source(repo_root)
        findings.extend(source_findings)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        findings.append(
            Finding(
                name="config-source",
                group=_GROUP,
                status="fail",
                message="No Harbor job config could be assembled from this repo",
                hint=(
                    f"Add a config with `harbor job init`, or a {PROFILE_FILENAME} naming a "
                    "task_template and datasets, or a directory of Harbor task dirs."
                ),
            )
        )
        return None, findings

    winner = min(candidates, key=lambda item: item.source.rank)
    passed_over = [item.source.kind for item in candidates if item is not winner]
    findings.append(
        Finding(
            name="config-source",
            group=_GROUP,
            status="pass",
            message=f"Using the {winner.source.kind} source: {winner.source.detail}",
            path=winner.source.path,
            hint=(f"Also found, lower trust: {', '.join(passed_over)}" if passed_over else None),
        )
    )
    return winner, findings


def _from_config_file(repo_root: Path) -> tuple[CandidateConfig | None, list[Finding]]:
    """A config file the user wrote, which is the strongest thing a repo can offer."""
    matches: list[tuple[Path, dict[str, Any]]] = []
    for relative in _CONFIG_SEARCH_DIRS:
        directory = repo_root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _CONFIG_SUFFIXES:
                continue
            payload = _load_mapping(path)
            if payload is not None and _looks_like_job_config(payload):
                matches.append((path, payload))

    if not matches:
        return None, []

    path, payload = matches[0]
    shown = display_path(path, repo_root)
    extra = [display_path(other, repo_root) for other, _ in matches[1:]]
    findings = [
        Finding(
            name="config-file",
            group=_GROUP,
            status="pass",
            message=f"Found a Harbor job config at {shown}",
            path=path,
            hint=(f"Ignoring additional candidates: {', '.join(extra)}" if extra else None),
        )
    ]
    return (
        CandidateConfig(
            data=payload,
            source=ConfigSource(
                kind="config_file",
                detail=f"declared at {shown}",
                path=path,
            ),
        ),
        findings,
    )


def _from_prior_job(repo_root: Path) -> tuple[CandidateConfig | None, list[Finding]]:
    """A ``config.json`` Harbor itself resolved and ran.

    Harbor writes ``config.json`` and ``lock.json`` into the job directory and again into
    every trial directory, so matching on those filenames alone would also pick up trial
    configs. ``_looks_like_job_config`` is the discriminator: a trial config names one
    ``task``, never a list of ``datasets`` or ``tasks``.
    """
    job_dirs: list[tuple[Path, dict[str, Any]]] = []
    for directory in walk_dirs(repo_root):
        config_path = directory / "config.json"
        if not config_path.is_file() or not (directory / "lock.json").is_file():
            continue
        payload = _load_mapping(config_path)
        if payload is not None and _looks_like_job_config(payload) and not _has_synthetic_agent(payload):
            job_dirs.append((config_path, payload))

    if not job_dirs:
        return None, []

    config_path, payload = max(job_dirs, key=lambda item: item[0].stat().st_mtime)
    shown = display_path(config_path.parent, repo_root)
    return (
        CandidateConfig(
            data=payload,
            source=ConfigSource(
                kind="prior_job",
                detail=f"resolved by a previous run at {shown}",
                path=config_path,
            ),
        ),
        [
            Finding(
                name="prior-job",
                group=_GROUP,
                status="pass",
                message=f"Found {len(job_dirs)} previous Harbor job config(s); using {shown}",
                path=config_path,
                hint="A config Harbor already ran is evidence, so it outranks anything inferred from layout.",
            )
        ],
    )


def _from_profile(repo_root: Path) -> tuple[CandidateConfig | None, list[Finding]]:
    """Assemble from ``optimizer.yaml`` plus the agent wrapper it implies."""
    profile_path = discover_profile(repo_root)
    if profile_path is None:
        return None, []

    try:
        profile = load_profile_model(profile_path, _DiscoveryProfile)
    except ProfileError as exc:
        return None, [
            Finding(
                name="profile",
                group=_GROUP,
                status="warn",
                message=f"Found {PROFILE_FILENAME} but could not read it: {exc}",
                path=profile_path,
            )
        ]

    findings = [
        Finding(
            name="profile",
            group=_GROUP,
            status="pass",
            message=f"Read {PROFILE_FILENAME}",
            path=profile_path,
        )
    ]

    # validation first: it is the eval set, and train exists to optimize against, so
    # preferring train here would quietly evaluate on the wrong split.
    declared = {"validation": profile.datasets.validation, "train": profile.datasets.train}
    evaluable = [(split, value) for split, value in declared.items() if value]
    if not evaluable:
        findings.append(
            Finding(
                name="profile-datasets",
                group=_GROUP,
                status="warn",
                message=f"{PROFILE_FILENAME} declares no datasets.train or datasets.validation",
                path=profile_path,
            )
        )
        return None, findings

    chosen_split, declared_value = evaluable[0]
    other_split = "train" if chosen_split == "validation" else "validation"
    also_declares = (
        f"{PROFILE_FILENAME} also declares datasets.{other_split}, which is not evaluated here."
        if declared[other_split]
        else None
    )
    registry_url = profile.datasets.registry_url

    if classify_dataset_value(declared_value, profile.profile_dir, registry_url=registry_url) == "ref":
        dataset_entry = _registry_dataset(declared_value, registry_url)
        findings.append(
            Finding(
                name="profile-datasets",
                group=_GROUP,
                # A ref is a legitimate way to declare a dataset, and one this machine may
                # have no reach to. Recorded as a warning rather than passed over in silence,
                # because a reader of the artifact cannot see the tasks the way they can for
                # a local path.
                status="warn",
                message=(
                    f"datasets.{chosen_split} is the registry ref '{declared_value}', "
                    f"which a run downloads rather than reads from this repo"
                ),
                path=profile_path,
                hint=" ".join(
                    filter(
                        None,
                        [
                            "Resolving it needs the registry to be reachable, and Harbor caches "
                            "it under ~/.cache/harbor on first use.",
                            also_declares,
                        ],
                    )
                ),
            )
        )
    else:
        dataset_path = _resolve_profile_path(declared_value, profile.profile_dir)
        if dataset_path is None:
            findings.append(
                Finding(
                    name="profile-datasets",
                    group=_GROUP,
                    status="warn",
                    message=f"Could not resolve datasets.{chosen_split} from {PROFILE_FILENAME}",
                    path=profile_path,
                )
            )
            return None, findings

        dataset_entry = {"path": str(dataset_path)}
        findings.append(
            Finding(
                name="profile-datasets",
                group=_GROUP,
                status="pass",
                message=f"Evaluating datasets.{chosen_split} at {display_path(dataset_path, repo_root)}",
                path=dataset_path,
                hint=also_declares,
            )
        )

    agent_root = _resolve_profile_path(profile.agent_source, profile.profile_dir) or repo_root
    agent = _agent_entry(agent_root, repo_root)
    findings.extend(agent.findings)

    return (
        CandidateConfig(
            data={"agents": [agent.data], "datasets": [dataset_entry]},
            source=ConfigSource(
                kind="profile",
                detail=f"assembled from {PROFILE_FILENAME} datasets.{chosen_split}",
                path=profile_path,
            ),
            agent_search_path=agent.search_path,
        ),
        findings,
    )


def _from_convention(repo_root: Path) -> tuple[CandidateConfig | None, list[Finding]]:
    """Assemble from directory layout alone, which is the weakest source on offer."""
    task_dirs = [directory for directory in walk_dirs(repo_root) if (directory / _TASK_CONFIG_FILENAME).is_file()]
    if not task_dirs:
        return None, []

    # Harbor takes the parent of task dirs as the dataset, and skips a child named
    # task_template, so a parent whose only task child is the template is a template
    # holder rather than a dataset.
    by_parent: dict[Path, list[Path]] = {}
    for task_dir in task_dirs:
        by_parent.setdefault(task_dir.parent, []).append(task_dir)

    dataset_dirs = {
        parent: children
        for parent, children in by_parent.items()
        if [child for child in children if child.name != _TEMPLATE_DIR_NAME]
    }
    if not dataset_dirs:
        return None, [
            Finding(
                name="convention-datasets",
                group=_GROUP,
                status="warn",
                message=f"Found Harbor task dirs but only under a {_TEMPLATE_DIR_NAME} directory",
                path=task_dirs[0],
                hint="A template is a scaffold for one task, not a dataset Harbor can evaluate.",
            )
        ]

    chosen = _preferred_dataset_dir(repo_root, dataset_dirs)
    shown = display_path(chosen, repo_root)
    findings = [
        Finding(
            name="convention-datasets",
            group=_GROUP,
            status="pass",
            message=f"Found {len(dataset_dirs[chosen])} Harbor task dir(s) under {shown}",
            path=chosen,
            hint="Inferred from directory layout, so confirm it is the set you meant to evaluate.",
        )
    ]

    agent = _agent_entry(repo_root, repo_root)
    findings.extend(agent.findings)

    return (
        CandidateConfig(
            data={"agents": [agent.data], "datasets": [{"path": str(chosen)}]},
            source=ConfigSource(
                kind="convention",
                detail=f"inferred from task dirs under {shown}",
                path=chosen,
            ),
            agent_search_path=agent.search_path,
        ),
        findings,
    )


def _preferred_dataset_dir(repo_root: Path, dataset_dirs: dict[Path, list[Path]]) -> Path:
    """Prefer a conventional eval directory, then the largest set, then a stable name."""
    for relative in _CONVENTIONAL_DATASET_DIRS:
        candidate = (repo_root / relative).resolve()
        if candidate in dataset_dirs:
            return candidate
    return max(dataset_dirs, key=lambda parent: (len(dataset_dirs[parent]), str(parent)))


class _AgentEntry(NamedTuple):
    """One ``agents`` entry, plus the search path the entry needs to be importable."""

    data: dict[str, Any]
    search_path: str | None
    findings: list[Finding]


def _agent_entry(agent_root: Path, repo_root: Path) -> _AgentEntry:
    """Describe the agent to run, preferring a wrapper in the repo over Harbor's default.

    Falls back to ``oracle``, which is what Harbor itself defaults to and the only agent
    that needs no model or credentials. It runs ``solution/solve.sh``, so a config that
    lands here still proves the tasks work even though it evaluates nothing.

    A wrapper yields a bare ``module:Class`` import path, which is what Harbor's own
    examples use, plus the directory holding that module. The directory is not decoration:
    Harbor imports through ``importlib.import_module`` and adds nothing to ``sys.path``, so
    a bare module name resolves only if something already put its directory there. Recording
    it is what lets the artifact hand out a run command that works, and a nested wrapper is
    why it cannot be assumed to be the repo root.
    """
    wrapper = _find_wrapper(agent_root) or _find_wrapper(repo_root)
    if wrapper is None:
        return _AgentEntry({"name": "oracle"}, None, [_no_wrapper_finding(agent_root, repo_root)])

    path, class_name = wrapper
    search_path = display_path(path.parent, repo_root)
    return _AgentEntry(
        {"import_path": f"{path.stem}:{class_name}"},
        search_path,
        [
            Finding(
                name="agent-entrypoint",
                group=_GROUP,
                status="pass",
                message=f"Agent import path {path.stem}:{class_name}, importable from {search_path}",
                path=path,
                hint=f"Read from the class definition in {display_path(path, repo_root)}, not assumed.",
            )
        ],
    )


def _no_wrapper_finding(agent_root: Path, repo_root: Path) -> Finding:
    """Say why the oracle is standing in, distinguishing no wrapper from no agent in one.

    The two read identically from the config and mean opposite things. A repo with no
    wrapper has nothing to evaluate yet; a repo whose wrapper this module could not
    recognize has an agent that is simply not being run, and reporting that as "no
    harbor_wrapper.py found" sends its author looking for a missing file.
    """
    unmatched = _wrapper_paths(agent_root) or _wrapper_paths(repo_root)
    oracle = (
        "The oracle replays solution/solve.sh, so it validates the tasks but evaluates no agent. "
        "Add a harbor_wrapper.py to evaluate yours."
    )
    if not unmatched:
        return Finding(
            name="agent-entrypoint",
            group=_GROUP,
            status="warn",
            message=f"No {_WRAPPER_FILENAME} found; falling back to Harbor's oracle agent",
            hint=oracle,
        )

    bases = " or ".join(sorted(_AGENT_BASE_CLASSES))
    return Finding(
        name="agent-entrypoint",
        group=_GROUP,
        status="warn",
        message=(
            f"{display_path(unmatched[0], repo_root)} declares no class based on {bases}; "
            "falling back to Harbor's oracle agent"
        ),
        path=unmatched[0],
        hint=(
            f"The base is matched by name in the source, so a wrapper reaching {bases} through an "
            "alias or an intermediate class is not recognized. A Harbor config file declaring the "
            "agent's import_path outranks this source, and would run it. " + oracle
        ),
    )


def _find_wrapper(root: Path) -> tuple[Path, str] | None:
    """Find ``harbor_wrapper.py`` and the agent class inside it, by parsing not importing.

    The class name is read rather than assumed: ``WrappedAgent`` is the convention in this
    repo, but a wrapper is a file the user wrote and the ladder's agent rung is the thing
    that gets to import it.
    """
    for path in _wrapper_paths(root):
        class_name = _agent_class_name(path)
        if class_name is not None:
            return path, class_name
    return None


def _wrapper_paths(root: Path) -> list[Path]:
    """Every ``harbor_wrapper.py`` under *root*, shallowest first."""
    return [directory / _WRAPPER_FILENAME for directory in walk_dirs(root) if (directory / _WRAPPER_FILENAME).is_file()]


def _agent_class_name(path: Path) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
            if name in _AGENT_BASE_CLASSES:
                return node.name
    return None


def classify_dataset_value(value: str, base_dir: Path, *, registry_url: str | None = None) -> DatasetKind:
    """Classify an ``optimizer.yaml`` dataset value as a local path or a Harbor registry ref.

    Mirrors ``nemo_experimentalist_plugin.resolve.classify_dataset_value``, which is the rule
    Experimentalist applies to the same file, so the two must agree — a value the optimizer
    downloads and discover resolves as a path yields an artifact about a directory nobody has.
    A copy rather than an import because Eval Author's dependency on Experimentalist is being
    removed rather than added to; ``test_sources.py`` pins the agreement instead.
    """
    if value.startswith(("./", "../", "/", "~")):
        return "path"
    if registry_url is not None:
        return "ref"
    if "/" in value:
        return "path"
    try:
        if (base_dir / value).exists():
            return "path"
    except OSError:  # not representable as a local path (e.g. name too long)
        pass
    return "ref"


def _registry_dataset(value: str, registry_url: str | None) -> dict[str, Any]:
    """A ``DatasetConfig`` naming a registry dataset, which is what Harbor resolves refs from.

    ``name`` and ``version`` rather than ``path``: Harbor's ``DatasetConfig`` rejects both at
    once, and a ref pointed at ``path`` is how the profile's ``name@version`` became a
    nonexistent directory under the profile dir.
    """
    name, separator, version = value.partition("@")
    entry: dict[str, Any] = {"name": name}
    if separator:
        entry["version"] = version
    if registry_url is not None:
        entry["registry_url"] = registry_url
    return entry


def _resolve_profile_path(value: str | None, profile_dir: Path) -> Path | None:
    if not value:
        return None
    try:
        return resolve_profile_path(value, profile_dir)
    except ProfileError:
        return None


def _has_synthetic_agent(payload: dict[str, Any]) -> bool:
    """Whether a config's agent only exists inside the process that wrote the config.

    Experimentalist's Harbor evaluator rewrites the agent's import path under a package it
    synthesizes in ``sys.modules`` for the duration of its own run, so the config it leaves
    behind names a module no separate ``harbor`` process can import. Harbor resolved and ran
    it, which is exactly what makes it tempting: without this guard, running the optimizer
    and then discover in the same repo reports "Harbor cannot run this repo's evals" about a
    repo that was just evaluated successfully.
    """
    agents = payload.get("agents")
    if not isinstance(agents, list):
        return False
    return any(
        isinstance(agent, dict)
        and isinstance(agent.get("import_path"), str)
        and agent["import_path"].startswith(f"{_AGENT_IMPORT_ROOT}.")
        for agent in agents
    )


def _looks_like_job_config(payload: dict[str, Any]) -> bool:
    """Whether a mapping declares a Harbor task source.

    Requiring ``datasets`` or ``tasks`` rather than ``agents`` does double duty: a job
    config without a task source cannot run at all, and the stricter test keeps unrelated
    YAML that happens to mention agents (a NAT workflow, a CI matrix) from matching.
    """
    for key in ("datasets", "tasks"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _load_mapping(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError):
        return None
    return payload if isinstance(payload, dict) else None


def read_profile_agent(profile_path: Path) -> str | None:
    """The agent name ``optimizer.yaml`` declares, if it declares one."""
    try:
        return load_profile_model(profile_path, _DiscoveryProfile).agent
    except ProfileError:
        return None
