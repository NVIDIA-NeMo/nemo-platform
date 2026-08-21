# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for reduced uv workspaces used by Docker image builds."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
WORKSPACE_SLICES = ("automodel", "rl", "unsloth")
WANDB_PACKAGE_SPEC_RE = re.compile(r"(?<![\w./-])wandb(?:\[[^\]]+\])?(?:==|~=|!=|<=|>=|<|>)[^\\\s\"']+")
DOCKER_IMAGE_WANDB_CONFIG_PATHS = (
    Path("docker/Dockerfile.nmp-customizer-tasks"),
    Path("docker/Dockerfile.safe-synthesizer-tasks"),
    Path("docker/automodel/Dockerfile.nmp-automodel-base"),
    Path("docker/automodel/no_override_requirements.txt"),
    Path("docker/unsloth/no_override_requirements.txt"),
)
RL_BASE_DOCKERFILE = ROOT / "docker/rl/Dockerfile.nmp-rl-base"


def _load_pyproject(path: Path) -> dict:
    with open(path, "rb") as pyproject:
        return tomllib.load(pyproject)


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _notice_wandb_version() -> str:
    for line in (ROOT / "NOTICE").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("wandb package version:"):
            return line.split(":", maxsplit=1)[1].strip()
    raise AssertionError("NOTICE does not document the wandb package version")


def _wandb_package_specs(path: Path) -> list[str]:
    specs: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line_without_comment = line.split("#", maxsplit=1)[0]
        specs.extend(WANDB_PACKAGE_SPEC_RE.findall(line_without_comment))
    return specs


def _workspace_sources(pyproject: dict) -> set[str]:
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    return {
        _normalize_package_name(name)
        for name, source in sources.items()
        if isinstance(source, dict) and source.get("workspace") is True
    }


@pytest.mark.parametrize(
    "path",
    [pytest.param(ROOT / path, id=str(path)) for path in DOCKER_IMAGE_WANDB_CONFIG_PATHS],
)
def test_distributed_image_wandb_specs_match_notice(path: Path) -> None:
    """Docker image wandb pins must match the wandb-core NOTICE metadata."""
    expected = f"wandb=={_notice_wandb_version()}"
    assert path.exists()

    specs = _wandb_package_specs(path)

    assert specs == [expected]


def test_rl_base_wandb_arg_matches_notice() -> None:
    """nmp-rl-base pins wandb via ARG so prefetch/cache purge stay on the NOTICE version."""
    expected = _notice_wandb_version()
    text = RL_BASE_DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"^ARG WANDB_VERSION=([0-9][0-9.]+)$", text, flags=re.MULTILINE)
    assert match is not None, "docker/rl/Dockerfile.nmp-rl-base must declare ARG WANDB_VERSION"
    assert match.group(1) == expected
    assert '"wandb==${WANDB_VERSION}"' in text
    assert "purge-stale-wandb-cache.sh" in text


@pytest.mark.parametrize("slice_name", WORKSPACE_SLICES)
def test_docker_workspace_slice_contains_all_workspace_sources(slice_name):
    """Every workspace source must name a package copied into the image slice."""
    workspace_path = ROOT / "docker" / slice_name / "pyproject.workspace.toml"
    workspace = _load_pyproject(workspace_path)
    member_paths = workspace["tool"]["uv"]["workspace"]["members"]
    member_projects = [
        (ROOT / member / "pyproject.toml", _load_pyproject(ROOT / member / "pyproject.toml")) for member in member_paths
    ]
    member_names = {_normalize_package_name(project["project"]["name"]) for _, project in member_projects}

    for project_path, project in [(workspace_path, workspace), *member_projects]:
        missing_sources = _workspace_sources(project) - member_names
        assert not missing_sources, (
            f"{slice_name} workspace is missing {sorted(missing_sources)} referenced by "
            f"{project_path.relative_to(ROOT)}"
        )


def test_deployments_plugin_is_optional_for_models_service():
    """The lazily loaded deployments backend must remain an optional package."""
    models = _load_pyproject(ROOT / "services/core/models/pyproject.toml")
    dependency_names = {
        _normalize_package_name(re.match(r"[A-Za-z0-9_.-]+", dependency).group())
        for dependency in models["project"]["dependencies"]
    }

    assert "nemo-deployments-plugin" not in dependency_names, (
        "nmp-models loads the deployments backend lazily, so nemo-deployments-plugin "
        "must not be an unconditional dependency"
    )
    assert "nemo-deployments-plugin" not in _workspace_sources(models), (
        "an optional package must not be declared as a required workspace source"
    )
