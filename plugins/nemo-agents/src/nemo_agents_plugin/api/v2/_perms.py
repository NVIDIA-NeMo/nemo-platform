# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed permission vocabulary for the agents plugin's hand-written routes.

Sub-namespaces under ``agents`` for the agent CRUD, deployment lifecycle, and gateway
proxy routes. The five job collections' permissions (``agents.evaluate.*`` etc.) are
stamped onto the factory routes and derived from there, so they are not declared here.
Route handlers reference these constants in their ``@path_rule``; the platform derives
the catalog from the routes.
"""

from __future__ import annotations

from nemo_platform_plugin.authz import PermissionSet, perm


class AgentPerms(PermissionSet, namespace="agents.agents"):
    CREATE = perm("Create agents")
    LIST = perm("List agents")
    READ = perm("Read an agent")
    DELETE = perm("Delete an agent")


class DeploymentPerms(PermissionSet, namespace="agents.deployments"):
    CREATE = perm("Create agent deployments")
    LIST = perm("List agent deployments")
    READ = perm("Read an agent deployment, including its logs and log stream")
    DELETE = perm("Delete an agent deployment")


class GatewayPerms(PermissionSet, namespace="agents.gateway"):
    INVOKE = perm("Invoke a deployed agent through the gateway proxy")
