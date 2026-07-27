# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed permission vocabulary for the Iron Swarm plugin routes.

Each ``perm(...)`` member mints a :class:`Permission` whose id is ``<namespace>.<member-lowercased>``
(or ``<namespace>.<suffix>`` when given). Referenced from ``@path_rule(permissions=[...])`` on the
route handlers — never as bare strings.
"""

from __future__ import annotations

from nemo_platform_plugin.authz import PermissionSet, perm


class IronSwarmRunPerms(PermissionSet, namespace="iron-swarm.runs"):
    LIST = perm("List Iron Swarm runs")
    READ = perm("Read an Iron Swarm run")
    DELETE = perm("Delete an Iron Swarm run record")
    APPLY = perm("Apply a run's hardened workflow to its agent")
    COMPOSE = perm("Compose a chosen subset of a run's recommended defenses")
    EVENTS_READ = perm("Stream an Iron Swarm run's live events", suffix="events.read")
    EVENTS_WRITE = perm("Ingest an Iron Swarm run's live events", suffix="events.write")


class IronSwarmManifestPerms(PermissionSet, namespace="iron-swarm.manifests"):
    LIST = perm("List Iron Swarm manifests")
    READ = perm("Read an Iron Swarm manifest")
    WRITE = perm("Create, update, or delete an Iron Swarm manifest")
    INSPECT = perm("Inspect projects/agents and validate model config for the create wizard")
