# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Progress reporting for RL training tasks.

Thin subclass of the shared
:class:`nmp.customization_common.training.progress.JobsServiceProgressReporter`
that bakes in the RL ``SERVICE_NAME`` so callers keep the
``JobsServiceProgressReporter(job_ctx)`` constructor. Mirrors the equivalent
modules in the unsloth and automodel services.
"""

from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.training.progress import (
    JobsServiceProgressReporter as _BaseJobsServiceProgressReporter,
)
from nmp.rl.app.constants import SERVICE_NAME

__all__ = ["JobsServiceProgressReporter"]


class JobsServiceProgressReporter(_BaseJobsServiceProgressReporter):
    """RL training progress reporter (binds the RL service name)."""

    def __init__(self, job_ctx: NMPJobContext):
        super().__init__(job_ctx, service_name=SERVICE_NAME)
