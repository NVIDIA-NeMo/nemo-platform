# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_customizer.shared.sdk.http import bind_backend


def test_http_helpers_build_unsloth_job_urls() -> None:
    http = bind_backend("unsloth")
    assert http._jobs_collection == "v2/workspaces/{workspace}/unsloth/jobs"
    assert http.healthz_path() == "v2/workspaces/{workspace}/unsloth/healthz"
    assert (
        http.job_status_path("https://nmp.test", "ws-a", "job-1")
        == "https://nmp.test/apis/customization/v2/workspaces/ws-a/unsloth/jobs/job-1"
    )


def test_http_helpers_build_automodel_job_urls() -> None:
    http = bind_backend("automodel")
    assert (
        http.job_status_path("https://nmp.test/", "default", "my-job")
        == "https://nmp.test/apis/customization/v2/workspaces/default/automodel/jobs/my-job"
    )
