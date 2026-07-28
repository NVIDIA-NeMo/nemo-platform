# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input resolution for one-command experiments.

Joins profile values with CLI overrides, normalizes insight references
(including the NeMo Insights producer's ``{"insights": [...]}`` local output),
and resolves dataset values (local paths or harbor registry refs). This module is the
Studio-parity seam: the CLI is a thin caller, and a future remote trigger
calls the same functions server-side.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.repository import looks_like_git
from nemo_experimentalist_plugin.profile import AgentProfile
from nemo_insights_plugin.contracts.insights import InsightsFileError, load_insights_document
from nemo_insights_plugin.contracts.profile import ProfileError, resolve_agent_spec_path, resolve_profile_path
from pydantic import BaseModel, Field, ValidationError, model_validator


class ResolveError(ValueError):
    """Experiment inputs could not be resolved from profile + overrides."""


class AgentSourceConfig(BaseModel):
    """Import-safe git/source modifiers for an experiment."""

    clone_depth: int | None = None
    source_path: str | None = None
    entrypoint: str | None = None


class CandidateStorageConfig(BaseModel):
    """Import-safe candidate persistence settings."""

    archive_candidates: bool = False
    candidate_branch_prefix: str = "optimizer"
    publish_winner: bool = False
    pr_draft: bool = True
    pr_base_branch: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    pr_labels: list[str] = Field(default_factory=list)


class GoalTreeConfig(BaseModel):
    """Import-safe goal-tree settings used by the optimizer loop."""

    max_depth: int = Field(default=3, gt=0)
    max_initial_depth: int = Field(default=2, gt=0)
    min_initial_nodes: int = Field(default=3, gt=0)
    max_initial_nodes: int = Field(default=4, gt=0)

    @model_validator(mode="after")
    def validate_constraints(self) -> GoalTreeConfig:
        if self.max_initial_depth > self.max_depth:
            raise ValueError(f"max_initial_depth ({self.max_initial_depth}) cannot exceed max_depth ({self.max_depth})")
        if self.min_initial_nodes > self.max_initial_nodes:
            raise ValueError(
                f"min_initial_nodes ({self.min_initial_nodes}) cannot exceed "
                f"max_initial_nodes ({self.max_initial_nodes})"
            )
        return self

    def validate_tree(self, tree: Any) -> Any:
        """Validate a runtime GoalTree without importing the agent module."""

        def visit(node: Any, depth: int) -> None:
            if depth > self.max_depth:
                raise ValueError(f"goal tree exceeds max depth {self.max_depth} at node {node.id!r}")
            if node.added_at_generation is None and depth > self.max_initial_depth:
                raise ValueError(
                    f"initial goal tree nodes exceed max depth {self.max_initial_depth} at node {node.id!r}"
                )
            for child in node.children:
                visit(child, depth + 1)

        visit(tree.root, 1)
        initial_nodes = [node for node in tree._iter_nodes() if node.added_at_generation is None]
        if not (self.min_initial_nodes <= len(initial_nodes) <= self.max_initial_nodes):
            raise ValueError(
                f"initial goal tree must have {self.min_initial_nodes}-"
                f"{self.max_initial_nodes} nodes, got {len(initial_nodes)}"
            )
        return tree


class CoderConfig(BaseModel):
    """Import-safe Coder tuning settings."""

    max_summary_tokens: int = 80_000
    max_fix_attempts: int = 2
    timeout_model_list_secs: float = 10.0
    model_catalog_path: Path | None = None


class RationalizerConfig(BaseModel):
    """Import-safe Rationalizer tuning settings."""

    max_summary_tokens: int = 80_000


class TraceAnalyzerConfig(BaseModel):
    """Import-safe trace-analysis tuning settings."""

    max_summary_tokens: int = 80_000


class AnalyzerConfig(BaseModel):
    """Import-safe AgentAnalyzer tuning settings."""

    max_summary_tokens: int = 80_000
    max_trials: int = 5
    max_divergent_pairs: int = 3
    rationalizer: RationalizerConfig = Field(default_factory=RationalizerConfig)
    trace_analyzer: TraceAnalyzerConfig = Field(default_factory=TraceAnalyzerConfig)


class ProposerConfig(BaseModel):
    """Import-safe Proposer tuning settings."""

    max_summary_tokens: int = 80_000


class EvolutionaryOptimizerConfig(BaseModel):
    """Complete import-safe schema for one optimizer run."""

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_curator_config(cls, data: Any) -> Any:
        if isinstance(data, dict) and "curator" in data:
            raise ValueError("'curator' was renamed to 'eval_author'; update the optimizer configuration")
        return data

    max_rounds: int = 15
    min_rounds_before_stopping: int = 3
    max_survivors: int = 3
    max_candidates: int = 3
    max_trajectory_tasks: int = 8
    max_train_batch_tasks: int | None = None
    train_batch_seed: int = 0
    max_summary_tokens: int = 80_000
    model_catalog_path: Path | None = None
    disable_trajectory_scoring: bool = False
    disable_convergence_check: bool = False
    source: AgentSourceConfig = Field(default_factory=AgentSourceConfig)
    storage: CandidateStorageConfig = Field(default_factory=CandidateStorageConfig)
    goal_config: GoalTreeConfig = Field(default_factory=GoalTreeConfig)
    coder: CoderConfig = Field(default_factory=CoderConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator: dict[str, Any] = Field(default_factory=dict)
    eval_author: EvalAuthorConfig = Field(default_factory=EvalAuthorConfig)


class EffectiveInsight(BaseModel):
    """The insight reference selected by flags and the shared profile default."""

    ref: str | None
    selector: str | None
    is_profile_default: bool = False


def resolve_effective_insight(
    *,
    profile: AgentProfile | None,
    insight: str | None,
    insight_id: str | None,
    disabled: bool = False,
) -> EffectiveInsight:
    """Resolve explicit/disabled/profile-default insight selection without I/O writes."""
    if disabled:
        if insight is not None or insight_id is not None:
            raise ResolveError("--no-insight cannot be combined with --insight or --insight-id")
        return EffectiveInsight(ref=None, selector=None)
    ref = insight
    is_default = False
    if ref is None and profile is not None:
        default_path = profile.profile_dir / ".nemo-optimizer" / "insights.yaml"
        if default_path.is_file():
            ref = str(default_path)
            is_default = True
    if insight_id is not None and ref is None:
        raise ResolveError(
            "--insight-id cannot be used without an insight; pass an explicit or shared local multi-insight file"
        )
    return EffectiveInsight(ref=ref, selector=insight_id, is_profile_default=is_default)


def _validate_json_insight(insight: dict[str, Any], source: str) -> dict[str, Any]:
    try:
        json.dumps(insight)
    except (TypeError, ValueError) as exc:
        raise ResolveError(f"{source} must be JSON-serializable: {exc}") from exc
    return insight


def parse_local_insights(ref: str) -> list[dict[str, Any]] | None:
    """Parse and validate a local insight file, or return ``None`` for a platform id."""
    path = Path(ref)
    if not path.is_file():
        return None
    try:
        payload = load_insights_document(path)
    except InsightsFileError as exc:
        raise ResolveError(str(exc)) from None
    if "insights" not in payload:
        return [_validate_json_insight(dict(payload), f"Insight in {path}")]
    raw_insights = payload["insights"]
    if not raw_insights:
        raise ResolveError(f"{ref} contains no insights")
    return [
        _validate_json_insight(dict(insight), f"Insight entry {index} in {path}")
        for index, insight in enumerate(raw_insights)
    ]


def select_local_insight(
    insights: list[dict[str, Any]],
    selector: str | None,
    ref: str,
) -> dict[str, Any]:
    """Select one insight by zero-based decimal index or exact id/title."""
    if selector is None:
        if len(insights) != 1:
            raise ResolveError(f"{ref} contains {len(insights)} insights; pass --insight-id. " + _candidates(insights))
        return insights[0]
    matches = [insight for insight in insights if selector in (insight.get("id"), insight.get("title"))]
    if len(matches) > 1:
        raise ResolveError(
            f"Insight selector {selector!r} is ambiguous in {ref} ({len(matches)} matches); "
            + _candidates(insights)
            + ". Use a zero-based index to disambiguate."
        )
    if matches:
        return matches[0]
    if selector.isdecimal():
        index = int(selector)
        if index >= len(insights):
            raise ResolveError(
                f"Insight index {index} is out of range for {ref} ({len(insights)} insights); " + _candidates(insights)
            )
        return insights[index]
    raise ResolveError(f"No insight matching {selector!r} in {ref}; " + _candidates(insights))


def normalize_insight_ref(ref: str, selector: str | None, scratch_dir: Path) -> str:
    """Return an insight reference the local backend can consume.

    Platform ids pass through. Every local file — a single-insight document or
    the NeMo Insights producer's ``{"insights": [...]}`` output (narrowed by ``selector``
    as a zero-based index or exact ``id``/``title``; unambiguous when the list
    has exactly one) — is rewritten as a single-insight JSON file under
    *scratch_dir*: the local backend reads insight files with ``json.loads``,
    so a YAML-authored file must not reach it raw.
    """
    insights = parse_local_insights(ref)
    if insights is None:
        if selector is not None:
            raise ResolveError(f"--insight-id requires a local multi-insight file; {ref!r} is not a local file")
        return ref
    selected = select_local_insight(insights, selector, ref)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out = scratch_dir / "insight.json"
    out.write_text(json.dumps(selected, indent=2), encoding="utf-8")
    return str(out)


def _candidates(insights: list[dict[str, Any]]) -> str:
    listing = ", ".join(f"{i.get('id', '?')} ({i.get('title', 'untitled')})" for i in insights)
    return f"Available: {listing}"


DEFAULT_DATASET_CACHE = Path.home() / ".cache" / "nemo-experimentalist" / "datasets"
CACHE_LAYOUT_VERSION = "v2"

DownloadFn = Callable[[str, Path, str | None], Awaitable[None]]


async def _harbor_download(name: str, output_dir: Path, registry_url: str | None) -> None:
    """Download a registry dataset via harbor into *output_dir*."""
    if "/" in name.partition("@")[0]:
        from harbor.registry.client.package import PackageDatasetClient  # noqa: PLC0415 - heavy import, CLI hot path

        client = PackageDatasetClient()
    else:
        from harbor.registry.client.factory import RegistryClientFactory  # noqa: PLC0415 - heavy import, CLI hot path

        client = RegistryClientFactory.create(registry_url=registry_url)
    await client.download_dataset(name, output_dir=output_dir, export=True)


DatasetKind = Literal["path", "ref"]


def classify_dataset_value(value: str, base_dir: Path, *, registry_url: str | None = None) -> DatasetKind:
    """Classify a dataset value as a local path or a harbor registry ref.

    Explicit paths (prefixed ``./ ../ / ~``) are always local. When a registry
    URL is configured, every other value is a registry ref, including
    namespaced refs containing ``/``. Without a registry URL, preserve the
    historical heuristic: values containing a path separator or naming an
    existing entry under *base_dir* are local paths.
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


def _cache_digest(value: str) -> str:
    """Return a bounded lowercase digest of the exact UTF-8 input bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dataset_cache_target(value: str, registry_url: str | None, cache: Path) -> Path:
    """Cache layout ``v2/<registry>/name-<digest>/<bare|version-<digest>>``."""
    name, separator, version = value.partition("@")
    registry_slug = hashlib.sha256(registry_url.encode()).hexdigest()[:12] if registry_url else "default"
    name_key = f"name-{_cache_digest(name)}"
    version_key = f"version-{_cache_digest(version)}" if separator else "bare"
    return cache / CACHE_LAYOUT_VERSION / registry_slug / name_key / version_key


async def resolve_dataset(
    value: str,
    profile_dir: Path,
    *,
    registry_url: str | None = None,
    cache_dir: Path | None = None,
    download: DownloadFn | None = None,
) -> str:
    """Resolve a dataset value to a local directory path (str).

    Local paths resolve against *profile_dir* and must exist. Registry refs
    (``name[@version]``) download to the cache directory on first use.
    """
    if classify_dataset_value(value, profile_dir, registry_url=registry_url) == "path":
        try:
            path = resolve_profile_path(value, profile_dir)
        except (ProfileError, RuntimeError) as exc:  # expanduser: ~user or unset HOME
            raise ResolveError(f"Dataset path {value!r} could not be resolved: {exc}") from None
        if not path.exists():
            raise ResolveError(f"Dataset path {value!r} does not exist (resolved to {path})")
        if not path.is_dir():
            raise ResolveError(f"Dataset path {value!r} is not a directory (resolved to {path})")
        return str(path)
    cache = cache_dir or DEFAULT_DATASET_CACHE
    target = _dataset_cache_target(value, registry_url, cache)
    if target.exists() and not target.is_dir():
        raise ResolveError(f"Dataset cache target for {value!r} is not a directory: {target}")
    if not target.exists():
        downloader = download or _harbor_download
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f"{target.name}.{uuid.uuid4().hex}.partial")
        try:
            try:
                await downloader(value, partial, registry_url)
            except ResolveError:
                raise
            except Exception as exc:
                raise ResolveError(f"Failed to download dataset {value!r}: {exc}") from exc
            if not partial.is_dir():
                raise ResolveError(f"Downloaded dataset {value!r} is not a directory: {partial}")
            try:
                partial.rename(target)  # atomic: cache path appears only on complete download
            except OSError as exc:
                if not target.is_dir():
                    raise ResolveError(f"Failed to publish downloaded dataset {value!r}: {exc}") from exc
        finally:
            if partial.is_symlink() or (partial.exists() and not partial.is_dir()):
                partial.unlink(missing_ok=True)
            elif partial.is_dir():
                shutil.rmtree(partial, ignore_errors=True)
    if not target.is_dir():
        raise ResolveError(f"Dataset cache target for {value!r} is not a directory: {target}")
    return str(target)


_PROFILE_SKELETON = """\
agent: <agent-name>            # must match the insight's agent
task_template: ./path/to/task_template
datasets:
  train: ./path/to/train       # local path or harbor registry ref
  validation: ./path/to/val
"""


class EffectiveExperimentPlan(BaseModel):
    """Pure effective values shared by Experiment and Doctor before downloads."""

    agent: str | None
    agent_spec: str | None
    insight: str | None
    insight_id: str | None
    train_dataset: str
    validation_dataset: str
    task_template: str | None
    train_anchor: Path
    validation_anchor: Path
    task_template_anchor: Path
    registry_url: str | None
    workspace: str
    config: EvolutionaryOptimizerConfig
    framework_skills_dirs: list[Path]


class ResolvedExperimentInputs(BaseModel):
    """Everything ``run_experimentalist`` needs after materialization."""

    agent: str | None
    agent_spec: str | None
    insight: str | None
    train_dataset: DatasetRef
    validation_dataset: DatasetRef
    task_template: DatasetRef | None
    workspace: str
    config: EvolutionaryOptimizerConfig
    framework_skills_dirs: list[Path]


def _read_agent_spec_path(spec: Path) -> str:
    try:
        spec.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ResolveError(f"Could not read agent_spec {spec}: {exc}") from None
    return str(spec)


def build_effective_experiment_plan(
    *,
    profile: AgentProfile | None,
    agent: str | None = None,
    agent_spec: str | None = None,
    insight: str | None = None,
    insight_id: str | None = None,
    no_insight: bool = False,
    train_dataset: str | None = None,
    validation_dataset: str | None = None,
    task_template: str | None = None,
    workspace: str | None = None,
    config_payload: Any | None = None,
    framework_skills: list[Path] | None = None,
) -> EffectiveExperimentPlan:
    """Build and validate the import-safe effective Experiment plan."""
    effective_insight = resolve_effective_insight(
        profile=profile,
        insight=insight,
        insight_id=insight_id,
        disabled=no_insight,
    )
    missing: list[str] = []
    profile_dir = profile.profile_dir if profile else Path.cwd()
    cwd = Path.cwd()
    train = train_dataset or (profile.datasets.train if profile else None)
    validation = validation_dataset or (profile.datasets.validation if profile else None)
    template = task_template or (profile.task_template if profile else None)
    train_anchor = cwd if train_dataset else profile_dir
    validation_anchor = cwd if validation_dataset else profile_dir
    template_anchor = cwd if task_template else profile_dir

    resolved_agent = agent
    if resolved_agent is not None and not looks_like_git(resolved_agent):
        resolved_agent = str(resolve_profile_path(resolved_agent, cwd))
    if resolved_agent is None and profile is not None:
        source = profile.agent_source
        resolved_agent = source if looks_like_git(source) else str(resolve_profile_path(source, profile_dir))

    if train is None:
        missing.append("--train-dataset")
    if validation is None:
        missing.append("--validation-dataset")
    if effective_insight.ref is not None and template is None:
        missing.append("--task-template")
    if effective_insight.ref is None and resolved_agent is None:
        missing.append("--agent")
    if missing:
        raise ResolveError(
            "Missing required inputs: " + ", ".join(missing) + ". Provide flags or add an "
            f"optimizer.yaml to the agent directory:\n{_PROFILE_SKELETON}"
        )
    assert train is not None and validation is not None

    if agent_spec is not None:
        spec = resolve_profile_path(agent_spec, cwd)
        if not spec.is_file():
            raise ResolveError(f"Explicit agent_spec {agent_spec!r} does not exist (resolved to {spec})")
        resolved_spec = _read_agent_spec_path(spec)
    elif profile is not None:
        resolved_spec = pick_agent_spec(profile)
    else:
        resolved_spec = None
    skills = (
        list(framework_skills)
        if framework_skills
        else [resolve_profile_path(skill, profile_dir) for skill in (profile.framework_skills if profile else [])]
    )
    return EffectiveExperimentPlan(
        agent=resolved_agent,
        agent_spec=resolved_spec,
        insight=effective_insight.ref,
        insight_id=effective_insight.selector,
        train_dataset=train,
        validation_dataset=validation,
        task_template=str(resolve_profile_path(template, template_anchor)) if template is not None else None,
        train_anchor=train_anchor,
        validation_anchor=validation_anchor,
        task_template_anchor=template_anchor,
        registry_url=profile.datasets.registry_url if profile else None,
        workspace=workspace or (profile.workspace if profile else "default"),
        config=_resolve_config(config_payload, profile),
        framework_skills_dirs=skills,
    )


async def resolve_experiment_inputs(
    *,
    profile: AgentProfile | None,
    scratch_dir: Path,
    agent: str | None = None,
    agent_spec: str | None = None,
    insight: str | None = None,
    insight_id: str | None = None,
    no_insight: bool = False,
    train_dataset: str | None = None,
    validation_dataset: str | None = None,
    task_template: str | None = None,
    workspace: str | None = None,
    config_payload: Any | None = None,
    framework_skills: list[Path] | None = None,
    download: DownloadFn | None = None,
    cache_dir: Path | None = None,
    plan: EffectiveExperimentPlan | None = None,
) -> ResolvedExperimentInputs:
    """Join CLI overrides with profile values (flag > profile > default)."""
    if plan is None:
        plan = build_effective_experiment_plan(
            profile=profile,
            agent=agent,
            agent_spec=agent_spec,
            insight=insight,
            insight_id=insight_id,
            no_insight=no_insight,
            train_dataset=train_dataset,
            validation_dataset=validation_dataset,
            task_template=task_template,
            workspace=workspace,
            config_payload=config_payload,
            framework_skills=framework_skills,
        )
    resolved_insight = (
        normalize_insight_ref(plan.insight, plan.insight_id, scratch_dir) if plan.insight is not None else None
    )

    if plan.train_dataset == plan.validation_dataset and plan.train_anchor == plan.validation_anchor:
        # Same ref for both: resolve once — two concurrent downloads would race
        # on the same cache .partial directory.
        train_uri = validation_uri = await resolve_dataset(
            plan.train_dataset,
            plan.train_anchor,
            registry_url=plan.registry_url,
            cache_dir=cache_dir,
            download=download,
        )
    else:
        train_uri, validation_uri = await asyncio.gather(
            resolve_dataset(
                plan.train_dataset,
                plan.train_anchor,
                registry_url=plan.registry_url,
                cache_dir=cache_dir,
                download=download,
            ),
            resolve_dataset(
                plan.validation_dataset,
                plan.validation_anchor,
                registry_url=plan.registry_url,
                cache_dir=cache_dir,
                download=download,
            ),
        )
    template_uri = (
        str(resolve_profile_path(plan.task_template, plan.task_template_anchor))
        if plan.task_template is not None
        else None
    )
    return ResolvedExperimentInputs(
        agent=plan.agent,
        agent_spec=plan.agent_spec,
        insight=resolved_insight,
        train_dataset=DatasetRef(uri=train_uri, metadata={"id": "train"}),
        validation_dataset=DatasetRef(uri=validation_uri, metadata={"id": "validation"}),
        task_template=DatasetRef(uri=template_uri, metadata={"id": "task-template"}) if template_uri else None,
        workspace=plan.workspace,
        config=plan.config,
        framework_skills_dirs=plan.framework_skills_dirs,
    )


def profile_storage_flags(profile: AgentProfile) -> dict:
    """Return validated, explicitly configured storage flags for Doctor."""
    return _resolve_config(None, profile).storage.model_dump(exclude_defaults=True)


def resolve_experiment_config(
    config_payload: Any | None,
    profile: AgentProfile | None,
) -> EvolutionaryOptimizerConfig:
    """Resolve and validate optimizer configuration without materializing inputs."""
    return _resolve_config(config_payload, profile)


def pick_agent_spec(profile: AgentProfile) -> str | None:
    """Resolve and read-check the configured or conventional agent spec."""
    try:
        spec = resolve_agent_spec_path(profile.profile_dir, profile.agent_spec)
    except ProfileError as exc:
        raise ResolveError(str(exc)) from None
    return _read_agent_spec_path(spec) if spec is not None else None


def _resolve_config(config_payload: Any | None, profile: AgentProfile | None) -> EvolutionaryOptimizerConfig:
    """Validate flag > profile-inline > profile-path > default config."""

    def validate(payload: Any, source: str) -> EvolutionaryOptimizerConfig:
        if not isinstance(payload, dict):
            raise ResolveError(f"Experiment config from {source} must be a YAML mapping, got {type(payload).__name__}")
        try:
            return EvolutionaryOptimizerConfig.model_validate(payload)
        except ValidationError as exc:
            raise ResolveError(f"Invalid experiment config from {source}: {exc}") from None

    if config_payload is not None:
        return validate(config_payload, "--config")
    if profile is None or profile.experiment_config is None:
        return EvolutionaryOptimizerConfig()
    if isinstance(profile.experiment_config, dict):
        return validate(profile.experiment_config, "profile experiment_config")
    config_path = resolve_profile_path(profile.experiment_config, profile.profile_dir)
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResolveError(f"Could not read experiment_config {config_path}: {exc}") from None
    return validate(payload, str(config_path))
