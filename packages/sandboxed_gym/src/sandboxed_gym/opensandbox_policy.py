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

"""OpenSandbox wire format for the shared egress policy.

Both sandbox tiers create OpenSandbox sandboxes and must render the same :class:`EgressPolicy`
into the same create block. Neither owns that rendering, so it lives beside the policy type
instead of inside one tier with the other importing across the seam.
"""

import ipaddress
from collections.abc import Mapping
from typing import Any

from sandboxed_gym.egress import EgressPolicy


NETWORK_POLICY_KEY = "network_policy"


def to_opensandbox_policy(policy: EgressPolicy) -> dict[str, Any]:
    """Render an egress policy in the shape the OpenSandbox sidecar expects."""
    return {
        "defaultAction": policy.default_action,
        "egress": [
            {"action": rule.action, "target": rule.target} for rule in policy.rules
        ],
    }


def create_options_with_policy(
    create: Mapping[str, Any] | None, policy: EgressPolicy
) -> dict[str, Any]:
    """Overlay our egress policy onto a deployment-supplied create block.

    The policy is applied last and unconditionally: whatever a deployment puts under
    ``network_policy``, ours is what reaches the SDK. Both tiers depend on that, so it is stated
    once here rather than reimplemented per tier.

    Args:
        create: Deployment-supplied create options, or ``None``.
        policy: The policy that must win.

    Returns:
        A new mapping; ``create`` is not mutated.
    """
    return {
        **(dict(create) if create else {}),
        NETWORK_POLICY_KEY: to_opensandbox_policy(policy),
    }


def canonical_egress_target(target: str) -> str:
    """Canonicalize an egress target so two spellings of the same range compare equal.

    The sidecar does not echo the policy it was given -- it re-serializes a merged one, with
    operator-managed always-rules and nameserver addresses folded in. Go renders an IPv4-mapped
    prefix as ``::ffff:0.0.0.0/96`` where we send ``::ffff:0:0/96``, and casing of IPv6 literals is
    not guaranteed either. Parsing both sides removes that class of false mismatch; anything that
    is not an address or network is treated as a domain.
    """
    try:
        return str(ipaddress.ip_network(target, strict=False))
    except ValueError:
        return target.strip().rstrip(".").lower()
