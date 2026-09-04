# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from nemo_platform_sdk_tools.sdk.core.openapi import OpenAPI, OpenAPIEndpoint
from nemo_platform_sdk_tools.sdk.core.stainless import StainlessConfig
from nemo_platform_sdk_tools.sdk.source_owned_resources import (
    SourceOwnedResource,
    derive_generated_schema_names,
    derive_source_owned_schema_names,
)
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[4]
JOBS_RESOURCE = SourceOwnedResource(resource_name="jobs", path_prefixes=("/apis/jobs/v2",))
PRESERVED_SHARED_SCHEMA_NAMES = {
    "PlatformJobLog",
    "PlatformJobLogPage",
}


def _schema_usage() -> dict[str, list[OpenAPIEndpoint]]:
    return OpenAPI.from_file(REPO_ROOT / "openapi" / "openapi.yaml").calculate_schema_to_endpoints()


def _stainless_config() -> StainlessConfig:
    return StainlessConfig.from_file(REPO_ROOT / "sdk" / "stainless.yaml")


def _load_stainless_config() -> dict[object, object]:
    yaml = YAML(typ="safe")
    config = yaml.load((REPO_ROOT / "sdk" / "stainless.yaml").read_text())
    assert isinstance(config, dict)
    return config


def _mapped_schema_names() -> set[str]:
    return {model.schema_name for model in _stainless_config().extract_models()}


def test_stainless_config_has_no_top_level_jobs_resource() -> None:
    resources = _load_stainless_config()["resources"]
    assert isinstance(resources, dict)

    assert "jobs" not in resources


def test_stainless_config_has_no_jobs_only_schema_mappings() -> None:
    jobs_only_schema_names = derive_source_owned_schema_names(_schema_usage(), (JOBS_RESOURCE,))

    assert jobs_only_schema_names.isdisjoint(_mapped_schema_names())


def test_stainless_config_keeps_shared_job_log_models_for_non_jobs_endpoints() -> None:
    generated_schema_names = derive_generated_schema_names(_schema_usage(), (JOBS_RESOURCE,))
    mapped_schema_names = _mapped_schema_names()

    assert PRESERVED_SHARED_SCHEMA_NAMES.issubset(generated_schema_names)
    assert PRESERVED_SHARED_SCHEMA_NAMES.issubset(mapped_schema_names)
