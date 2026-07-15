# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Jobs service.

Wraps the endpoint functions from ``jobs.endpoints`` as direct methods using
the ``method()`` descriptor, following the example-plugin / Files pattern.

Usage::

    from nemo_platform_plugin.jobs.client import JobsClient
    from nemo_platform_plugin.jobs.types import CreatePlatformJobRequest

    client = JobsClient(base_url="...", workspace="default")
    resp = client.create_job(body=CreatePlatformJobRequest(...))
    job = resp.data()

    for job in client.list_jobs().items():
        print(job.name)

    with client.download_job_result(job="j-1", name="out").stream() as chunks:
        for chunk in chunks:
            ...
"""

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.jobs import endpoints


class _JobsMethods:
    # Execution profiles
    get_execution_profiles = method(endpoints.get_execution_profiles)

    # Job CRUD + lifecycle
    create_job = method(endpoints.create_job)
    list_jobs = method(endpoints.list_jobs)
    get_job = method(endpoints.get_job)
    delete_job = method(endpoints.delete_job)
    cancel_job = method(endpoints.cancel_job)
    pause_job = method(endpoints.pause_job)
    resume_job = method(endpoints.resume_job)

    # Job status
    get_job_status = method(endpoints.get_job_status)
    update_job_status_details = method(endpoints.update_job_status_details)

    # Job logs
    list_job_logs = method(endpoints.list_job_logs)

    # Job results
    create_job_result = method(endpoints.create_job_result)
    list_job_results = method(endpoints.list_job_results)
    get_job_result = method(endpoints.get_job_result)
    download_job_result = method(endpoints.download_job_result)

    # Job steps
    list_steps = method(endpoints.list_steps)
    get_job_step = method(endpoints.get_job_step)
    update_job_step_status = method(endpoints.update_job_step_status)

    # Job tasks
    list_job_step_tasks = method(endpoints.list_job_step_tasks)
    update_job_step_task = method(endpoints.update_job_step_task)
    get_job_step_task = method(endpoints.get_job_step_task)


class JobsClient(_JobsMethods, NemoClient):
    """Sync client for the Jobs service API."""


class AsyncJobsClient(_JobsMethods, AsyncNemoClient):
    """Async client for the Jobs service API."""
