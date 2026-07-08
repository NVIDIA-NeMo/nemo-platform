# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Route-derived authorization for the Intake plugin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

from fastapi import APIRouter
from fastapi.routing import APIRoute
from nemo_platform_plugin.authz import AuthzScope, CallerKind, Permission, PermissionSet, path_rule, perm

scope = AuthzScope("intake")


class IntakePerms(PermissionSet, namespace="intake"):
    """Permissions retained from Intake's former static authz entries."""

    ANNOTATIONS_CREATE = perm("Create intake annotations", suffix="annotations.create")
    ANNOTATIONS_DELETE = perm("Delete intake annotations", suffix="annotations.delete")
    ANNOTATIONS_LIST = perm("List intake annotations", suffix="annotations.list")
    ANNOTATIONS_READ = perm("Read intake annotations", suffix="annotations.read")
    EVALUATOR_RESULTS_CREATE = perm("Create intake evaluator results", suffix="evaluator-results.create")
    EVALUATOR_RESULTS_LIST = perm("List intake evaluator results", suffix="evaluator-results.list")
    EVALUATOR_RESULTS_READ = perm("Read intake evaluator results", suffix="evaluator-results.read")
    EXPERIMENT_GROUPS_CREATE = perm("Create intake experiment groups", suffix="experiment-groups.create")
    EXPERIMENT_GROUPS_DELETE = perm("Delete intake experiment groups", suffix="experiment-groups.delete")
    EXPERIMENT_GROUPS_READ = perm("Read intake experiment groups", suffix="experiment-groups.read")
    EXPERIMENT_GROUPS_UPDATE = perm("Update intake experiment groups", suffix="experiment-groups.update")
    EXPERIMENTS_CREATE = perm("Create intake experiments", suffix="experiments.create")
    EXPERIMENTS_DELETE = perm("Delete intake experiments", suffix="experiments.delete")
    EXPERIMENTS_READ = perm("Read intake experiments", suffix="experiments.read")
    EXPERIMENTS_UPDATE = perm("Update intake experiments", suffix="experiments.update")
    INGEST_CREATE = perm("Ingest traces into intake", suffix="ingest.create")
    SPANS_LIST = perm("List intake spans", suffix="spans.list")
    SPANS_READ = perm("Read intake spans", suffix="spans.read")
    TRACES_READ = perm("Read intake traces", suffix="traces.read")


ScopeKind = Literal["read", "write"]
RouteRule = tuple[ScopeKind, Permission]

_AUTHZ_STAMPED_ATTR: Final[str] = "__nemo_intake_authz_stamped__"

_ROUTE_AUTHZ: Final[Mapping[str, Mapping[str, RouteRule]]] = {
    "/v2/workspaces/{workspace}/annotations": {
        "get": ("read", IntakePerms.ANNOTATIONS_LIST),
        "post": ("write", IntakePerms.ANNOTATIONS_CREATE),
    },
    "/v2/workspaces/{workspace}/annotations/{annotation_id}": {
        "delete": ("write", IntakePerms.ANNOTATIONS_DELETE),
        "get": ("read", IntakePerms.ANNOTATIONS_READ),
    },
    "/v2/workspaces/{workspace}/evaluator-results": {
        "get": ("read", IntakePerms.EVALUATOR_RESULTS_LIST),
        "post": ("write", IntakePerms.EVALUATOR_RESULTS_CREATE),
    },
    "/v2/workspaces/{workspace}/evaluator-results/{evaluator_result_id}": {
        "get": ("read", IntakePerms.EVALUATOR_RESULTS_READ),
    },
    "/v2/workspaces/{workspace}/experiment-groups": {
        "get": ("read", IntakePerms.EXPERIMENT_GROUPS_READ),
        "post": ("write", IntakePerms.EXPERIMENT_GROUPS_CREATE),
    },
    "/v2/workspaces/{workspace}/experiment-groups/{name}": {
        "delete": ("write", IntakePerms.EXPERIMENT_GROUPS_DELETE),
        "get": ("read", IntakePerms.EXPERIMENT_GROUPS_READ),
        "put": ("write", IntakePerms.EXPERIMENT_GROUPS_UPDATE),
    },
    "/v2/workspaces/{workspace}/experiments": {
        "get": ("read", IntakePerms.EXPERIMENTS_READ),
        "post": ("write", IntakePerms.EXPERIMENTS_CREATE),
    },
    "/v2/workspaces/{workspace}/experiments/{name}": {
        "delete": ("write", IntakePerms.EXPERIMENTS_DELETE),
        "get": ("read", IntakePerms.EXPERIMENTS_READ),
        "put": ("write", IntakePerms.EXPERIMENTS_UPDATE),
    },
    "/v2/workspaces/{workspace}/experiments/{name}/pin": {
        "delete": ("write", IntakePerms.EXPERIMENTS_UPDATE),
        "post": ("write", IntakePerms.EXPERIMENTS_UPDATE),
    },
    "/v2/workspaces/{workspace}/experiments/{name}/sessions": {
        "get": ("read", IntakePerms.EXPERIMENTS_READ),
    },
    "/v2/workspaces/{workspace}/ingest/atif": {
        "post": ("write", IntakePerms.INGEST_CREATE),
    },
    "/v2/workspaces/{workspace}/ingest/chat-completions": {
        "post": ("write", IntakePerms.INGEST_CREATE),
    },
    "/v2/workspaces/{workspace}/ingest/otlp/v1/traces": {
        "post": ("write", IntakePerms.INGEST_CREATE),
    },
    "/v2/workspaces/{workspace}/spans": {
        "get": ("read", IntakePerms.SPANS_LIST),
    },
    "/v2/workspaces/{workspace}/spans/groups": {
        "get": ("read", IntakePerms.SPANS_READ),
    },
    "/v2/workspaces/{workspace}/spans/{span_id}": {
        "get": ("read", IntakePerms.SPANS_READ),
    },
    "/v2/workspaces/{workspace}/spans/{span_id}/evaluator-results": {
        "get": ("read", IntakePerms.EVALUATOR_RESULTS_LIST),
    },
    "/v2/workspaces/{workspace}/traces": {
        "get": ("read", IntakePerms.TRACES_READ),
    },
    "/v2/workspaces/{workspace}/traces/{id}": {
        "get": ("read", IntakePerms.TRACES_READ),
    },
}


def apply_intake_authz(router: APIRouter) -> None:
    """Stamp Intake routes with the authz rules they had as a builtin service."""

    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue

        method_rules = _ROUTE_AUTHZ.get(route.path)
        if method_rules is None:
            raise ValueError(f"Intake route {route.path!r} is missing authz metadata")

        methods = {method.lower() for method in route.methods or set()}
        for method in methods:
            if method not in method_rules:
                raise ValueError(f"Intake route {method.upper()} {route.path!r} is missing authz metadata")

        route_scope_kinds = {method_rules[method][0] for method in methods}
        if len(route_scope_kinds) > 1:
            raise ValueError(f"Intake route {route.path!r} mixes read/write scopes on one handler")

        stamped = route.endpoint.__dict__.setdefault(_AUTHZ_STAMPED_ATTR, set())
        for method in methods:
            stamp_key = (route.path, method)
            if stamp_key in stamped:
                continue
            scope_kind, permission = method_rules[method]
            (scope.write if scope_kind == "write" else scope.read)(route.endpoint)
            path_rule(callers=[CallerKind.PRINCIPAL], permissions=[permission])(route.endpoint)
            stamped.add(stamp_key)
