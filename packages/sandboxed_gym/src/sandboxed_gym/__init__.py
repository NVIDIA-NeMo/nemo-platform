# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Trusted episode broker + sandboxed Gym host orchestrator.

Ray wrappers live under :mod:`sandboxed_gym.ray` (optional extra). The HTTP
surface, sanitizer, backends, and orchestrator are importable without Ray.
"""

from sandboxed_gym.backends.base import (
    EpisodeSandboxBackend,
    SanitizedEpisodeSpec,
    UnsupportedEpisodeOperationError,
)
from sandboxed_gym.broker import EpisodeBrokerServer
from sandboxed_gym.config import BrokerEndpoint, EpisodeBrokerConfig
from sandboxed_gym.egress import (
    DEFAULT_PUBLIC_DNS_SUFFIXES,
    EgressAllowlist,
    EgressPolicy,
    EgressRule,
    build_egress_policy,
    denied_cidrs,
    local_resolver_addresses,
)
from sandboxed_gym.errors import BrokerRequestError
from sandboxed_gym.host.models import (
    GymHostEgressRule,
    GymHostHandle,
    GymHostSpec,
    GymHostVolumeMount,
    NemoGymSandboxedConfig,
    SandboxConfig,
)
from sandboxed_gym.http_app import (
    begin_shutdown,
    build_broker_app,
    close_all_episodes,
)
from sandboxed_gym.orchestrator import (
    SandboxedGymOrchestrator,
    SandboxedGymSession,
    apply_sandbox_runtime_defaults,
)
from sandboxed_gym.sanitize import (
    sanitize_create_request,
    sanitize_exec_request,
)
from sandboxed_gym.serve_config import (
    SandboxedGymServeConfig,
    SandboxedGymSessionDescriptor,
)


__all__ = [
    "DEFAULT_PUBLIC_DNS_SUFFIXES",
    "BrokerEndpoint",
    "BrokerRequestError",
    "EgressAllowlist",
    "EgressPolicy",
    "EgressRule",
    "EpisodeBrokerConfig",
    "EpisodeBrokerServer",
    "EpisodeSandboxBackend",
    "GymHostEgressRule",
    "GymHostHandle",
    "GymHostSpec",
    "GymHostVolumeMount",
    "NemoGymSandboxedConfig",
    "SandboxConfig",
    "SanitizedEpisodeSpec",
    "SandboxedGymOrchestrator",
    "SandboxedGymServeConfig",
    "SandboxedGymSession",
    "SandboxedGymSessionDescriptor",
    "UnsupportedEpisodeOperationError",
    "apply_sandbox_runtime_defaults",
    "begin_shutdown",
    "build_broker_app",
    "build_egress_policy",
    "denied_cidrs",
    "local_resolver_addresses",
    "close_all_episodes",
    "sanitize_create_request",
    "sanitize_exec_request",
]
