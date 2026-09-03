# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Submit-time Gym environment FileSet contract (wheels-v1 only)."""

import pytest
from nemo_evaluator.jobs.gym_environment_package import (
    NATIVE_V1_UNSUPPORTED_MESSAGE,
    GymEnvironmentPackageError,
    parse_environment_manifest,
    require_supported_environment_format,
    validate_environment_manifest_against_listing,
)

NATIVE_MANIFEST = """
format: native-v1
config_paths:
  - resources_servers/custom/configs/custom.yaml
metadata:
  name: custom
"""

WHEELS_MANIFEST = """
format: wheels-v1
config_paths:
  - resources_servers/custom/configs/custom.yaml
metadata:
  name: custom
"""

WHEELS_LISTING = [
    "nemo-environment.yaml",
    "resources_servers/custom/configs/custom.yaml",
    "wheels/custom_dependency-1.0-py3-none-any.whl",
]


def test_wheels_v1_manifest_is_accepted_against_a_valid_listing() -> None:
    manifest = parse_environment_manifest(WHEELS_MANIFEST)
    require_supported_environment_format(manifest)
    validate_environment_manifest_against_listing(manifest, WHEELS_LISTING)


def test_native_v1_is_parseable_and_rejected_as_unsupported() -> None:
    manifest = parse_environment_manifest(NATIVE_MANIFEST)

    with pytest.raises(GymEnvironmentPackageError, match="native-v1 environment packages are not supported"):
        require_supported_environment_format(manifest)
    assert str(GymEnvironmentPackageError(NATIVE_V1_UNSUPPORTED_MESSAGE)) == NATIVE_V1_UNSUPPORTED_MESSAGE


@pytest.mark.parametrize(
    "raw_manifest",
    [
        "format: adapter-wheels-v1\nconfig_paths: [configs/test.yaml]\nmetadata: {name: test}\n",
        "format: native-v1\nconfig_paths: []\nmetadata: {name: test}\n",
        "format: native-v1\nconfig_paths: [../test.yaml]\nmetadata: {name: test}\n",
        "format: wheels-v1\nconfig_paths: [configs/test.yaml]\n",
    ],
)
def test_invalid_manifests_are_rejected(raw_manifest: str) -> None:
    with pytest.raises(GymEnvironmentPackageError):
        parse_environment_manifest(raw_manifest)


@pytest.mark.parametrize(
    ("listing", "error"),
    [
        (["nemo-environment.yaml", "resources_servers/custom/configs/custom.yaml"], "non-empty wheels/ directory"),
        (
            [
                "nemo-environment.yaml",
                "resources_servers/custom/configs/custom.yaml",
                "wheels/requirements.txt",
            ],
            "non-wheel files",
        ),
        (
            [
                "nemo-environment.yaml",
                "resources_servers/custom/configs/custom.yaml",
                "responses_api_models/customer/configs/customer.yaml",
                "wheels/custom_dependency-1.0-py3-none-any.whl",
            ],
            "model configuration is operator-owned",
        ),
        (["nemo-environment.yaml"], "config_paths reference files that are not in the package"),
        (
            [
                "nemo-environment.yaml",
                "resources_servers/custom/configs/custom.yaml",
                "training.jsonl",
                "wheels/custom_dependency-1.0-py3-none-any.whl",
            ],
            "prompt JSONL",
        ),
    ],
)
def test_wheels_listing_rejections(listing: list[str], error: str) -> None:
    manifest = parse_environment_manifest(WHEELS_MANIFEST)
    with pytest.raises(GymEnvironmentPackageError, match=error):
        validate_environment_manifest_against_listing(manifest, listing)
