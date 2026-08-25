# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
import tomlkit
from nemo_platform_sdk_tools.sdk import post_generation_update
from nemo_platform_sdk_tools.sdk.core.common import SdkInfo


def _sdk_info(tmp_path: Path) -> SdkInfo:
    return SdkInfo(
        sdks_root_dir=tmp_path / "sdk",
        package_name="nemo-platform-sdk",
        directory_name="nemo-platform",
        module_name="nemo_platform",
        sdk_dir=tmp_path / "sdk/python/nemo-platform",
        overrides_dir=tmp_path / "sdk/python/overrides/nemo-platform",
        readme_dir=tmp_path / "sdk/python/overrides/nemo-platform/README",
        stainless_config_file=tmp_path / "sdk/stainless.yaml",
        openapi_spec_file=tmp_path / "openapi/openapi.yaml",
    )


def _write_minimal_sdk_pyproject(sdk_info: SdkInfo) -> None:
    sdk_info.sdk_dir.mkdir(parents=True)
    (sdk_info.sdk_dir / "pyproject.toml").write_text(
        """
[project]
name = "nemo-platform-sdk"
authors = [{ name = "Old Author" }]
classifiers = [
  "Programming Language :: Python :: 3.8",
  "Programming Language :: Python :: 3.12",
]
dependencies = ["exceptiongroup>=1", "httpx>=0.23.0"]
version = "0.0.0"

[project.urls]
Homepage = "https://example.invalid"

[tool.ruff]

[tool.pyright]

[tool.pytest.ini_options]
addopts = ""

[tool.uv]
conflicts = []

[dependency-groups]
pydantic-v1 = []

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]

[tool.hatch.build.targets.wheel]
force-include = { "old" = "target" }
""".lstrip(),
        encoding="utf-8",
    )


def test_update_pyproject_requires_build_hook_override(tmp_path: Path) -> None:
    sdk_info = _sdk_info(tmp_path)
    _write_minimal_sdk_pyproject(sdk_info)

    with pytest.raises(FileNotFoundError, match="hatch_build.py"):
        post_generation_update.update_pyproject_toml(sdk_info)


def test_update_pyproject_copies_build_hook_before_configuring_path(tmp_path: Path) -> None:
    sdk_info = _sdk_info(tmp_path)
    _write_minimal_sdk_pyproject(sdk_info)
    sdk_info.overrides_dir.mkdir(parents=True)
    source_hook = sdk_info.overrides_dir / "hatch_build.py"
    source_hook.write_text("# build hook\n", encoding="utf-8")

    assert post_generation_update.update_pyproject_toml(sdk_info)

    destination_hook = sdk_info.sdk_dir / "hatch_build.py"
    assert destination_hook.read_text(encoding="utf-8") == "# build hook\n"

    pyproject = tomlkit.loads((sdk_info.sdk_dir / "pyproject.toml").read_text(encoding="utf-8"))
    targets = pyproject["tool"]["hatch"]["build"]["targets"]
    wheel_hook = targets["wheel"]["hooks"]["custom"]
    sdist_hook = targets["sdist"]["hooks"]["custom"]
    assert wheel_hook["path"] == "hatch_build.py"
    assert sdist_hook["path"] == "hatch_build.py"
    assert list(wheel_hook["source-packages"]) == list(sdist_hook["source-packages"])
