# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_platform_sdk_tools.sdk.core.openapi import OpenAPIEndpoint
from nemo_platform_sdk_tools.sdk.source_owned_resources import (
    SourceOwnedResource,
    active_source_owned_resources,
    derive_generated_schema_names,
    derive_source_owned_schema_names,
    endpoint_is_source_owned,
    filter_schema_usage_for_generated_resources,
)

WIDGETS = SourceOwnedResource(resource_name="widgets", path_prefixes=("/apis/widgets/v2",))


def _endpoint(path: str) -> OpenAPIEndpoint:
    return OpenAPIEndpoint(method="get", path=path)


def test_active_source_owned_resources_only_includes_absent_resources() -> None:
    active_resources = active_source_owned_resources(
        configured_resource_names={"files"},
        source_owned_resources=(
            WIDGETS,
            SourceOwnedResource(resource_name="files", path_prefixes=("/apis/files/v2",)),
        ),
    )

    assert active_resources == (WIDGETS,)


def test_endpoint_is_source_owned_uses_path_boundaries() -> None:
    assert endpoint_is_source_owned(_endpoint("/apis/widgets/v2/workspaces/default/widgets"), (WIDGETS,))
    assert endpoint_is_source_owned(_endpoint("/apis/widgets/v2"), (WIDGETS,))
    assert not endpoint_is_source_owned(_endpoint("/apis/widgets/v20/workspaces/default/widgets"), (WIDGETS,))
    assert not endpoint_is_source_owned(_endpoint("/apis/files/v2/workspaces/default/files"), (WIDGETS,))


def test_derive_source_owned_schema_names_excludes_shared_schemas() -> None:
    schema_usage = {
        "WidgetCreateRequest": [_endpoint("/apis/widgets/v2/workspaces/default/widgets")],
        "SharedLogPage": [
            _endpoint("/apis/widgets/v2/workspaces/default/widgets/widget/logs"),
            _endpoint("/apis/files/v2/workspaces/default/files/file/logs"),
        ],
        "FilePage": [_endpoint("/apis/files/v2/workspaces/default/files")],
    }

    assert derive_source_owned_schema_names(schema_usage, (WIDGETS,)) == {"WidgetCreateRequest"}
    assert derive_generated_schema_names(schema_usage, (WIDGETS,)) == {"SharedLogPage", "FilePage"}


def test_filter_schema_usage_for_generated_resources_removes_source_owned_endpoints() -> None:
    schema_usage = {
        "WidgetCreateRequest": [_endpoint("/apis/widgets/v2/workspaces/default/widgets")],
        "SharedLogPage": [
            _endpoint("/apis/widgets/v2/workspaces/default/widgets/widget/logs"),
            _endpoint("/apis/files/v2/workspaces/default/files/file/logs"),
        ],
    }

    assert filter_schema_usage_for_generated_resources(schema_usage, (WIDGETS,)) == {
        "SharedLogPage": [_endpoint("/apis/files/v2/workspaces/default/files/file/logs")]
    }
