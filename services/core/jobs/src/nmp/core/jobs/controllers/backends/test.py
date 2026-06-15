# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Generic, Literal, TypeVar

from nemo_platform.types.jobs import PlatformJobStepWithContext
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.app.providers import ContainerExecutionProvider
from nmp.core.jobs.app.schemas import BaseExecutionProfile
from nmp.core.jobs.controllers.backends.base import JobBackend, JobExecutionProfileConfig, JobUpdate
from nmp.core.jobs.controllers.backends.docker import DockerJobExecutionProfileConfig
from nmp.core.jobs.controllers.backends.kubernetes import KubernetesJobExecutionProfileConfig
from pydantic import Field

ProviderT = TypeVar("ProviderT", bound=ContainerExecutionProvider)


class E2EJobExecutionProfile(BaseExecutionProfile):
    """
    Execution configuration for E2E testing.
    This backend auto-completes jobs without actually running containers,
    making tests fast and deterministic.
    """

    backend: Literal["e2e"] = "e2e"
    config: JobExecutionProfileConfig = Field(
        default_factory=JobExecutionProfileConfig,
        description="Configuration for the e2e test executor",
    )

    @property
    def supports_persistent_storage(self) -> bool:
        """E2E backend claims to support persistent storage since jobs auto-complete without execution."""
        return True


class MockJobBackend(Generic[ProviderT]):
    """
    Provides a backend that can be used for testing
    """

    def init(self):
        self.schedule_calls = []
        self.sync_calls = []

    def schedule(
        self,
        executor_config: ProviderT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        logging.info(f"Scheduling job {step.job} with step {step.name} using executor config")
        self.schedule_calls.append({"executor_config": executor_config, "step": step})
        return JobUpdate(status=PlatformJobStatus.PENDING)

    def sync(self, step: PlatformJobStepWithContext) -> JobUpdate:
        logging.info(f"Syncing job {step.job} with current status: {step.status}")

        status = PlatformJobStatus.CREATED
        if step.status == PlatformJobStatus.PENDING:
            status = PlatformJobStatus.ACTIVE
        elif step.status == PlatformJobStatus.ACTIVE:
            status = PlatformJobStatus.COMPLETED
        elif step.status == PlatformJobStatus.PAUSING:
            status = PlatformJobStatus.PAUSED

        logging.info(f"Job {step.job} status updated to: {status}")
        self.sync_calls.append({"step": step, "status": status})

        return JobUpdate(status=status)


class TestE2EJobBackend(JobBackend[ProviderT, JobExecutionProfileConfig], Generic[ProviderT]):
    def init(self):
        self.mock = MockJobBackend()
        self.mock.init()

    def shutdown(self):
        return

    def schedule(
        self,
        executor_config: ProviderT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self.mock.schedule(executor_config, step)

    def sync(self, step: PlatformJobStepWithContext) -> JobUpdate:
        return self.mock.sync(step)

    def cleanup_steps(self):
        return


class MockDockerJobBackend(JobBackend[ProviderT, DockerJobExecutionProfileConfig], Generic[ProviderT]):
    def init(self):
        self.mock = MockJobBackend()
        self.mock.init()

    def shutdown(self):
        return

    def schedule(
        self,
        executor_config: ProviderT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self.mock.schedule(executor_config, step)

    def sync(self, step: PlatformJobStepWithContext) -> JobUpdate:
        return self.mock.sync(step)

    def cleanup_steps(self):
        return


class MockKubernetesJobBackend(JobBackend[ProviderT, KubernetesJobExecutionProfileConfig], Generic[ProviderT]):
    def init(self):
        self.mock = MockJobBackend()
        self.mock.init()

    def shutdown(self):
        return

    def schedule(
        self,
        executor_config: ProviderT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self.mock.schedule(executor_config, step)

    def sync(self, step: PlatformJobStepWithContext) -> JobUpdate:
        return self.mock.sync(step)

    def cleanup_steps(self):
        return


class TestE2ECPUJobBackend(TestE2EJobBackend[ContainerExecutionProvider]):
    pass


class TestE2EGPUJobBackend(TestE2EJobBackend[ContainerExecutionProvider]):
    pass


class MockDockerCPUJobBackend(MockDockerJobBackend[ContainerExecutionProvider]):
    pass


class MockDockerGPUJobBackend(MockDockerJobBackend[ContainerExecutionProvider]):
    pass


class MockKubernetesCPUJobBackend(MockKubernetesJobBackend[ContainerExecutionProvider]):
    pass


class MockKubernetesGPUJobBackend(MockKubernetesJobBackend[ContainerExecutionProvider]):
    pass
