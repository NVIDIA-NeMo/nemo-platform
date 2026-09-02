# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from __future__ import annotations

from typing_extensions import TypedDict

__all__ = ["StepLifecycleParam"]


class StepLifecycleParam(TypedDict, total=False):
    """Controller-level lifecycle configuration for a job step.

    These settings control how the jobs controller manages the step,
    as opposed to ``config`` which is the task payload forwarded to
    the container.
    """

    staleness_timeout_seconds: int
    """
    If every active task in the step goes this many seconds without an update, the
    step is terminated. A value of 0 disables staleness detection.
    """
