# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-generation Jobs SDK compatibility shim.

Jobs are source-owned and intentionally excluded from Stainless generation.
The public Python SDK still exposes the last generated Jobs resource and model
surface so existing Customizer docs and users do not need to migrate in the
same PR.
"""

from __future__ import annotations

from pathlib import Path

import typer
from nemo_platform_sdk_tools.sdk.core.common import get_sdk_info

CLIENT_SNIPPETS: tuple[tuple[str, str, str], ...] = (
    (
        "sync Jobs client resource",
        "    def jobs(self) -> JobsResource:\n",
        """\
    @cached_property
    def jobs(self) -> JobsResource:
        from .resources.jobs import JobsResource

        return JobsResource(self)

""",
    ),
    (
        "async Jobs client resource",
        "    def jobs(self) -> AsyncJobsResource:\n",
        """\
    @cached_property
    def jobs(self) -> AsyncJobsResource:
        from .resources.jobs import AsyncJobsResource

        return AsyncJobsResource(self)

""",
    ),
    (
        "sync raw Jobs response resource",
        "    def jobs(self) -> jobs.JobsResourceWithRawResponse:\n",
        """\
    @cached_property
    def jobs(self) -> jobs.JobsResourceWithRawResponse:
        from .resources.jobs import JobsResourceWithRawResponse

        return JobsResourceWithRawResponse(self._client.jobs)

""",
    ),
    (
        "async raw Jobs response resource",
        "    def jobs(self) -> jobs.AsyncJobsResourceWithRawResponse:\n",
        """\
    @cached_property
    def jobs(self) -> jobs.AsyncJobsResourceWithRawResponse:
        from .resources.jobs import AsyncJobsResourceWithRawResponse

        return AsyncJobsResourceWithRawResponse(self._client.jobs)

""",
    ),
    (
        "sync streaming Jobs response resource",
        "    def jobs(self) -> jobs.JobsResourceWithStreamingResponse:\n",
        """\
    @cached_property
    def jobs(self) -> jobs.JobsResourceWithStreamingResponse:
        from .resources.jobs import JobsResourceWithStreamingResponse

        return JobsResourceWithStreamingResponse(self._client.jobs)

""",
    ),
    (
        "async streaming Jobs response resource",
        "    def jobs(self) -> jobs.AsyncJobsResourceWithStreamingResponse:\n",
        """\
    @cached_property
    def jobs(self) -> jobs.AsyncJobsResourceWithStreamingResponse:
        from .resources.jobs import AsyncJobsResourceWithStreamingResponse

        return AsyncJobsResourceWithStreamingResponse(self._client.jobs)

""",
    ),
)

CLIENT_INSERT_ANCHORS: dict[str, str] = {
    "sync Jobs client resource": "    @cached_property\n    def models(self) -> ModelsResource:\n",
    "async Jobs client resource": "    @cached_property\n    def models(self) -> AsyncModelsResource:\n",
    "sync raw Jobs response resource": (
        "    @cached_property\n    def models(self) -> models.ModelsResourceWithRawResponse:\n"
    ),
    "async raw Jobs response resource": (
        "    @cached_property\n    def models(self) -> models.AsyncModelsResourceWithRawResponse:\n"
    ),
    "sync streaming Jobs response resource": (
        "    @cached_property\n    def models(self) -> models.ModelsResourceWithStreamingResponse:\n"
    ),
    "async streaming Jobs response resource": (
        "    @cached_property\n    def models(self) -> models.AsyncModelsResourceWithStreamingResponse:\n"
    ),
}

CLIENT_TYPE_IMPORTS = (
    ("        jobs,", "        auth,\n"),
    (
        "    from .resources.jobs.jobs import JobsResource, AsyncJobsResource",
        "    from .resources.auth.auth import AuthResource, AsyncAuthResource\n",
    ),
)

TOP_LEVEL_EXPORT_INSERTIONS = (
    ("    FileStorageType as FileStorageType,", "    FilesetMetadata as FilesetMetadata,\n"),
    ("    PlatformJobStatus as PlatformJobStatus,", "    GenericSortField as GenericSortField,\n"),
    (
        "    PlatformJobResultResponse as PlatformJobResultResponse,",
        "    DatasetMetadataContent as DatasetMetadataContent,\n",
    ),
    (
        "    PlatformJobStatusResponse as PlatformJobStatusResponse,",
        "    PlatformJobResultResponse as PlatformJobResultResponse,\n",
    ),
    (
        "    PlatformJobListResultResponse as PlatformJobListResultResponse,",
        "    ToolCallingMetadataContent as ToolCallingMetadataContent,\n",
    ),
    (
        "    PlatformJobStepStatusResponse as PlatformJobStepStatusResponse,",
        "    PlatformJobListResultResponse as PlatformJobListResultResponse,\n",
    ),
    (
        "    PlatformJobTaskStatusResponse as PlatformJobTaskStatusResponse,",
        "    PlatformJobStepStatusResponse as PlatformJobStepStatusResponse,\n",
    ),
)

SHARED_EXPORT_INSERTIONS = (
    (
        "from .file_storage_type import FileStorageType as FileStorageType",
        "from .api_endpoint_data import APIEndpointData as APIEndpointData\n",
    ),
    (
        "from .platform_job_status import PlatformJobStatus as PlatformJobStatus",
        "from .generic_sort_field import GenericSortField as GenericSortField\n",
    ),
    (
        "from .platform_job_result_response import PlatformJobResultResponse as PlatformJobResultResponse",
        "from .environment_metadata_content import EnvironmentMetadataContent as EnvironmentMetadataContent\n",
    ),
    (
        "from .platform_job_status_response import PlatformJobStatusResponse as PlatformJobStatusResponse",
        "from .platform_job_result_response import PlatformJobResultResponse as PlatformJobResultResponse\n",
    ),
    (
        "from .platform_job_list_result_response import PlatformJobListResultResponse as PlatformJobListResultResponse",
        "from .workload_token_exchange_response import WorkloadTokenExchangeResponse as WorkloadTokenExchangeResponse\n",
    ),
    (
        "from .platform_job_step_status_response import PlatformJobStepStatusResponse as PlatformJobStepStatusResponse",
        "from .platform_job_list_result_response import PlatformJobListResultResponse as PlatformJobListResultResponse\n",
    ),
    (
        "from .platform_job_task_status_response import PlatformJobTaskStatusResponse as PlatformJobTaskStatusResponse",
        "from .platform_job_step_status_response import PlatformJobStepStatusResponse as PlatformJobStepStatusResponse\n",
    ),
)

SHARED_PARAM_EXPORT_INSERTIONS = (
    (
        "from .file_storage_type import FileStorageType as FileStorageType",
        "from .api_endpoint_data import APIEndpointData as APIEndpointData\n",
    ),
    (
        "from .platform_job_status import PlatformJobStatus as PlatformJobStatus",
        "from .generic_sort_field import GenericSortField as GenericSortField\n",
    ),
)

API_SHARED_TYPES = (
    "FileStorageType",
    "PlatformJobListResultResponse",
    "PlatformJobResultResponse",
    "PlatformJobStatus",
    "PlatformJobStatusResponse",
    "PlatformJobStepStatusResponse",
    "PlatformJobTaskStatusResponse",
)

JOBS_API_LINK = "# [Jobs](src/nemo_platform/resources/jobs/api.md)"


def _insert_once(content: str, *, name: str, marker: str, snippet: str, anchor: str) -> tuple[str, bool]:
    if marker in content:
        return content, False
    if anchor not in content:
        raise RuntimeError(f"Could not find anchor for {name}: {anchor!r}")
    return content.replace(anchor, snippet + anchor, 1), True


def _remove_compat_export_block(content: str) -> str:
    lines = content.splitlines()
    try:
        marker_index = lines.index("# Jobs compatibility exports.")
    except ValueError:
        return content

    return "\n".join(lines[:marker_index]).rstrip() + "\n"


def _insert_missing_lines(path: Path, insertions: tuple[tuple[str, str], ...]) -> bool:
    original_content = path.read_text(encoding="utf-8")
    content = original_content
    content = _remove_compat_export_block(content)

    for line, anchor in insertions:
        if line in content:
            continue
        if anchor not in content:
            raise RuntimeError(f"Could not find anchor for Jobs compatibility export: {anchor!r}")
        content = content.replace(anchor, anchor + line + "\n", 1)

    if content == original_content:
        return False

    path.write_text(content, encoding="utf-8")
    return True


def _inject_client_properties(client_path: Path) -> list[str]:
    original_content = client_path.read_text(encoding="utf-8")
    content = original_content
    content = _remove_compat_type_checking_block(content)
    updated = content != original_content
    injected: list[str] = []

    for line, anchor in CLIENT_TYPE_IMPORTS:
        if line in content:
            continue
        if anchor not in content:
            raise RuntimeError(f"Could not find anchor for Jobs TYPE_CHECKING import: {anchor!r}")
        content = content.replace(anchor, anchor + line + "\n", 1)
        updated = True
        injected.append("Jobs TYPE_CHECKING imports")

    for name, marker, snippet in CLIENT_SNIPPETS:
        content, snippet_updated = _insert_once(
            content,
            name=name,
            marker=marker,
            snippet=snippet,
            anchor=CLIENT_INSERT_ANCHORS[name],
        )
        updated = updated or snippet_updated
        if snippet_updated:
            injected.append(name)

    if updated:
        client_path.write_text(content, encoding="utf-8")

    return injected


def _remove_compat_type_checking_block(content: str) -> str:
    compat_block = """\
if TYPE_CHECKING:
    from .resources import jobs
    from .resources.jobs.jobs import JobsResource, AsyncJobsResource

"""
    return content.replace(compat_block, "")


def _inject_api_md(api_path: Path) -> bool:
    content = api_path.read_text(encoding="utf-8")
    updated = False

    import_start = "from nemo_platform.types import (\n"
    import_end = ")\n```"
    start = content.find(import_start)
    end = content.find(import_end, start)
    if start == -1 or end == -1:
        raise RuntimeError("Could not find shared types import block in api.md")

    block_start = start + len(import_start)
    shared_type_lines = content[block_start:end].splitlines()
    shared_types = {line.strip().removesuffix(",") for line in shared_type_lines if line.strip()}
    updated_types = shared_types.union(API_SHARED_TYPES)
    rendered_types = "".join(f"    {type_name},\n" for type_name in sorted(updated_types))
    if rendered_types != content[block_start:end]:
        content = content[:block_start] + rendered_types + content[end:]
        updated = True

    if JOBS_API_LINK not in content:
        content = content.replace(
            "# [Models](src/nemo_platform/resources/models/api.md)",
            f"{JOBS_API_LINK}\n\n# [Models](src/nemo_platform/resources/models/api.md)",
            1,
        )
        updated = True

    if updated:
        api_path.write_text(content, encoding="utf-8")

    return updated


def inject_jobs_compat() -> None:
    """Restore public Jobs SDK imports and client properties after generation."""
    sdk_info = get_sdk_info()
    package_root = sdk_info.sdk_dir / "src" / sdk_info.module_name

    typer.echo("Injecting Jobs SDK compatibility shim...")

    injected = _inject_client_properties(package_root / "_client.py")
    for name in injected:
        typer.echo(f"  - Injected {name}")

    export_files = (
        (package_root / "types" / "__init__.py", TOP_LEVEL_EXPORT_INSERTIONS),
        (package_root / "types" / "shared" / "__init__.py", SHARED_EXPORT_INSERTIONS),
        (package_root / "types" / "shared_params" / "__init__.py", SHARED_PARAM_EXPORT_INSERTIONS),
    )
    for path, insertions in export_files:
        if _insert_missing_lines(path, insertions):
            typer.echo(f"  - Updated {path.relative_to(sdk_info.sdk_dir)}")

    if _inject_api_md(sdk_info.sdk_dir / "api.md"):
        typer.echo("  - Updated api.md")

    typer.echo("Jobs SDK compatibility shim completed!")
