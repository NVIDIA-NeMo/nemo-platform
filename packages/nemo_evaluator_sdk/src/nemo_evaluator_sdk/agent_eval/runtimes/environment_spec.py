# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Declarative environment authoring for agent-eval tasks.

Moves task authoring away from an implicit "Dockerfile per task" toward a small,
declarative ``environment.yaml`` spec, while keeping a Dockerfile escape hatch.

Spec shape (``environment.yaml`` in the task dir)::

    environment:
      image: nemo-platform-agentic-base:2026.06
      profile: evaluator-platform
      dependencies:
        python:
          - pytest
          - nemo-evaluator-sdk
      setup:
        - seed-providers
        - create-workspace

Escape hatch::

    environment:
      dockerfile: environment/Dockerfile

Resolution is deliberately minimal: a spec is turned into a :class:`BuildPlan`
(a Dockerfile + build context + target tag). The Dockerfile path is used as-is;
an ``image``-based spec generates a tiny derived Dockerfile (``FROM <image>`` plus
optional ``pip install``). ``setup`` steps are carried as plan metadata — they are
runtime concerns handled outside the image build — so this module does not
execute them.

``yaml`` is imported lazily so that importing this module costs nothing for
callers that never load a spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ENVIRONMENT_SPEC_FILENAME = "environment.yaml"
DEFAULT_DOCKERFILE_RELPATH = "environment/Dockerfile"


@dataclass(frozen=True)
class EnvironmentSpec:
    """Declarative environment for one task (or a Dockerfile escape hatch)."""

    image: str | None = None
    profile: str | None = None
    python_dependencies: list[str] = field(default_factory=list)
    setup: list[str] = field(default_factory=list)
    dockerfile: Path | None = None

    def __post_init__(self) -> None:
        if self.dockerfile is None and self.image is None:
            raise ValueError("environment spec requires either 'image' or 'dockerfile'")


def load_environment_spec(task_dir: str | Path) -> EnvironmentSpec:
    """Load a task's environment spec.

    Resolution order:
    1. ``environment.yaml`` in the task dir (declarative spec, preferred).
    2. ``environment/Dockerfile`` (backward-compatible escape hatch so existing
       tasks work without authoring a spec).
    """
    root = Path(task_dir)
    spec_path = root / ENVIRONMENT_SPEC_FILENAME
    if spec_path.is_file():
        import yaml

        return _parse_spec(yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}, root)

    dockerfile = root / DEFAULT_DOCKERFILE_RELPATH
    if dockerfile.is_file():
        return EnvironmentSpec(dockerfile=dockerfile)

    raise FileNotFoundError(
        f"No environment defined for task {root}: expected {ENVIRONMENT_SPEC_FILENAME} or {DEFAULT_DOCKERFILE_RELPATH}"
    )


def _parse_spec(payload: dict, task_dir: Path) -> EnvironmentSpec:
    data = payload.get("environment", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid environment spec in {task_dir}: expected a mapping")

    dockerfile_value = data.get("dockerfile")
    dockerfile = None
    if dockerfile_value:
        dockerfile = Path(dockerfile_value)
        if not dockerfile.is_absolute():
            dockerfile = (task_dir / dockerfile).resolve()
        if not dockerfile.is_file():
            raise FileNotFoundError(f"environment.dockerfile not found: {dockerfile}")

    dependencies = data.get("dependencies") or {}
    python_deps = dependencies.get("python") if isinstance(dependencies, dict) else None

    return EnvironmentSpec(
        image=data.get("image"),
        profile=data.get("profile"),
        python_dependencies=list(python_deps or []),
        setup=list(data.get("setup") or []),
        dockerfile=dockerfile,
    )


@dataclass(frozen=True)
class BuildPlan:
    """A resolved, executable Docker build for one task."""

    image_tag: str
    dockerfile: Path
    context_dir: Path
    generated: bool
    base_image: str | None = None
    setup: list[str] = field(default_factory=list)


def plan_task_build(
    task_dir: str | Path,
    image_tag: str,
    *,
    spec: EnvironmentSpec | None = None,
    generated_dir: Path | None = None,
) -> BuildPlan:
    """Resolve a task's environment spec into a concrete :class:`BuildPlan`.

    For the Dockerfile escape hatch the existing Dockerfile/context is used. For
    an ``image``-based spec a minimal derived Dockerfile is written under
    ``generated_dir`` (defaults to ``<task_dir>/.agentic-build``).
    """
    root = Path(task_dir)
    spec = spec or load_environment_spec(root)

    if spec.dockerfile is not None:
        return BuildPlan(
            image_tag=image_tag,
            dockerfile=spec.dockerfile,
            context_dir=spec.dockerfile.parent,
            generated=False,
            setup=list(spec.setup),
        )

    # image-based spec: generate a tiny derived Dockerfile.
    context_dir = generated_dir if generated_dir is not None else (root / ".agentic-build")
    context_dir.mkdir(parents=True, exist_ok=True)
    dockerfile = context_dir / "Dockerfile"
    dockerfile.write_text(render_derived_dockerfile(spec), encoding="utf-8")
    return BuildPlan(
        image_tag=image_tag,
        dockerfile=dockerfile,
        context_dir=context_dir,
        generated=True,
        base_image=spec.image,
        setup=list(spec.setup),
    )


def execute_build_plan(plan: BuildPlan) -> None:
    """Build the Docker image described by ``plan``."""
    from nemo_evaluator_sdk.agent_eval.runtimes.docker import build_dockerfile

    build_dockerfile(plan.dockerfile, plan.context_dir, plan.image_tag)


def render_derived_dockerfile(spec: EnvironmentSpec) -> str:
    """Render a minimal derived Dockerfile from an image-based spec."""
    if spec.image is None:
        raise ValueError("cannot render a derived Dockerfile without a base image")
    lines = [f"FROM {spec.image}"]
    if spec.profile:
        lines.append(f"LABEL com.nvidia.agentic.profile={spec.profile}")
    if spec.python_dependencies:
        deps = " ".join(spec.python_dependencies)
        lines.append(f"RUN pip install --no-cache-dir {deps}")
    if spec.setup:
        # Setup steps are runtime concerns; record them for provenance only.
        lines.append(f'LABEL com.nvidia.agentic.setup="{",".join(spec.setup)}"')
    return "\n".join(lines) + "\n"
