# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization job endpoints using job_route_factory."""

import logging

from nemo_platform_plugin.jobs.api_factory import JobRouteOption, job_route_factory
from nmp.customizer.api.v2.jobs.schemas import CustomizationJobInput, CustomizationJobOutput
from nmp.customizer.app.jobs.compiler import platform_job_config_compiler
from nmp.customizer.utils import generate_customization_id, transform_input_to_output

logger = logging.getLogger(__name__)


# Export the jobs router directly - prefix will be added by service.py
# SDK is injected via FastAPI dependency injection (get_sdk_client)
#
# Uses separate input/output types:
# - CustomizationJobInput: What users provide in POST (no output_fileset)
# - CustomizationJobOutput: What gets stored and returned (with output_fileset)
# - transform_input_to_output: Uses job_name for output_fileset and output_name
# - generate_customization_id: Generates job name when user doesn't provide one
router = job_route_factory(
    service_name="customization",
    job_type="Customization",
    job_input=CustomizationJobInput,
    job_output=CustomizationJobOutput,
    input_to_output=transform_input_to_output,
    platform_job_config_compiler=platform_job_config_compiler,
    generate_job_name=generate_customization_id,
    route_options=[JobRouteOption.CORE],
)
