# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from nemo_platform_sdk_tools.sdk import post_generation_jobs_compat
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


def _write_minimal_sdk(sdk_info: SdkInfo) -> None:
    package_root = sdk_info.sdk_dir / "src" / "nemo_platform"
    (package_root / "types" / "shared").mkdir(parents=True)
    (package_root / "types" / "shared_params").mkdir(parents=True)

    (package_root / "_client.py").write_text(
        """
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .resources import (
        auth,
        models,
    )
    from .resources.auth.auth import AuthResource, AsyncAuthResource
    from .resources.models import ModelsResource, AsyncModelsResource

__all__ = [
    "NeMoPlatform",
    "AsyncNeMoPlatform",
]

class NeMoPlatform:
    @cached_property
    def models(self) -> ModelsResource:
        from .models import ModelsResource

        return ModelsResource(self)

class AsyncNeMoPlatform:
    @cached_property
    def models(self) -> AsyncModelsResource:
        from .models import AsyncModelsResource

        return AsyncModelsResource(self)

class NeMoPlatformWithRawResponse:
    @cached_property
    def models(self) -> models.ModelsResourceWithRawResponse:
        from .resources.models import ModelsResourceWithRawResponse

        return ModelsResourceWithRawResponse(self._client.models)

class AsyncNeMoPlatformWithRawResponse:
    @cached_property
    def models(self) -> models.AsyncModelsResourceWithRawResponse:
        from .resources.models import AsyncModelsResourceWithRawResponse

        return AsyncModelsResourceWithRawResponse(self._client.models)

class NeMoPlatformWithStreamedResponse:
    @cached_property
    def models(self) -> models.ModelsResourceWithStreamingResponse:
        from .resources.models import ModelsResourceWithStreamingResponse

        return ModelsResourceWithStreamingResponse(self._client.models)

class AsyncNeMoPlatformWithStreamedResponse:
    @cached_property
    def models(self) -> models.AsyncModelsResourceWithStreamingResponse:
        from .resources.models import AsyncModelsResourceWithStreamingResponse

        return AsyncModelsResourceWithStreamingResponse(self._client.models)
""".lstrip(),
        encoding="utf-8",
    )
    (package_root / "types" / "__init__.py").write_text(
        """
from __future__ import annotations

from .shared import (
    APIEndpointData as APIEndpointData,
    DatasetMetadataContent as DatasetMetadataContent,
    FilesetMetadata as FilesetMetadata,
    GenericSortField as GenericSortField,
    ToolCallingMetadataContent as ToolCallingMetadataContent,
)
""".lstrip(),
        encoding="utf-8",
    )
    (package_root / "types" / "shared" / "__init__.py").write_text(
        """
from .api_endpoint_data import APIEndpointData as APIEndpointData
from .environment_metadata_content import EnvironmentMetadataContent as EnvironmentMetadataContent
from .generic_sort_field import GenericSortField as GenericSortField
from .platform_job_log import PlatformJobLog as PlatformJobLog
from .tool_calling_metadata_content import ToolCallingMetadataContent as ToolCallingMetadataContent
from .workload_token_exchange_response import WorkloadTokenExchangeResponse as WorkloadTokenExchangeResponse
""".lstrip(),
        encoding="utf-8",
    )
    (package_root / "types" / "shared_params" / "__init__.py").write_text(
        """
from .api_endpoint_data import APIEndpointData as APIEndpointData
from .generic_sort_field import GenericSortField as GenericSortField
from .model_spec import ModelSpec as ModelSpec
""".lstrip(),
        encoding="utf-8",
    )
    (sdk_info.sdk_dir / "api.md").write_text(
        """
```python
from nemo_platform.types import (
    PlatformJobLogPage,
    PromptData,
)
```

# [Models](src/nemo_platform/resources/models/api.md)
""".lstrip(),
        encoding="utf-8",
    )


def test_inject_jobs_compat_restores_client_and_type_exports(tmp_path: Path, monkeypatch) -> None:
    sdk_info = _sdk_info(tmp_path)
    _write_minimal_sdk(sdk_info)
    monkeypatch.setattr(post_generation_jobs_compat, "get_sdk_info", lambda: sdk_info)

    post_generation_jobs_compat.inject_jobs_compat()
    post_generation_jobs_compat.inject_jobs_compat()

    client = (sdk_info.sdk_dir / "src" / "nemo_platform" / "_client.py").read_text(encoding="utf-8")
    assert client.count("def jobs(self) -> JobsResource:") == 1
    assert client.count("def jobs(self) -> AsyncJobsResource:") == 1
    assert client.count("def jobs(self) -> jobs.JobsResourceWithRawResponse:") == 1
    assert client.count("from .resources.jobs.jobs import JobsResource, AsyncJobsResource") == 1

    shared = (sdk_info.sdk_dir / "src" / "nemo_platform" / "types" / "shared" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "from .platform_job_status_response import PlatformJobStatusResponse as PlatformJobStatusResponse" in shared

    top_level = (sdk_info.sdk_dir / "src" / "nemo_platform" / "types" / "__init__.py").read_text(encoding="utf-8")
    assert "    PlatformJobResultResponse as PlatformJobResultResponse," in top_level
    assert "# Jobs compatibility exports." not in top_level

    api_md = (sdk_info.sdk_dir / "api.md").read_text(encoding="utf-8")
    assert "PlatformJobStatusResponse," in api_md
    assert "# [Jobs](src/nemo_platform/resources/jobs/api.md)" in api_md
