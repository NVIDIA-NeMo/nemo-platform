# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP helpers for Automodel customization SDK resources."""

from nemo_customizer.shared.sdk.http import CustomizationHttpHelpers, PlatformClient, bind_backend

_http = bind_backend("automodel")

base_url = _http.base_url
resolve_workspace = _http.resolve_workspace
url = _http.url
jobs_collection_url = _http.jobs_collection_url
job_url = _http.job_url
platform_default_headers = CustomizationHttpHelpers.platform_default_headers
create_job_payload = CustomizationHttpHelpers.create_job_payload

__all__ = [
    "PlatformClient",
    "base_url",
    "create_job_payload",
    "job_url",
    "jobs_collection_url",
    "platform_default_headers",
    "resolve_workspace",
    "url",
]
