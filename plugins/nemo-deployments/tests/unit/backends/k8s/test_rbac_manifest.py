# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assert the deploy chart's controller Role grants the k8s backend's required RBAC.

The chart under ``k8s/helm`` declares an unconditional ``k8s-nim-operator`` chart
dependency, so ``helm template`` cannot render without that subchart present in
``charts/`` (fetched from an NGC repo) — a network dependency this suite must not
require. Assertions instead parse the static YAML rule entries directly out of the
Go-template source, which is safe because the base RBAC rules (unlike the
Volcano/NIM-Operator blocks) are plain YAML with no Helm expressions inside them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_CONTROLLER_ROLE_RELATIVE_PATH = Path("k8s", "helm", "templates", "core", "controller-role.yaml")


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / _CONTROLLER_ROLE_RELATIVE_PATH).is_file():
            return parent
    raise FileNotFoundError(f"Could not locate repo root containing {_CONTROLLER_ROLE_RELATIVE_PATH}")


def _controller_role_source() -> str:
    role_path = _repo_root() / _CONTROLLER_ROLE_RELATIVE_PATH
    content = role_path.read_text()
    # Only the Role definition (before the "---" separator) is relevant; the
    # RoleBinding that follows has no `rules:` block to collide with.
    role_section, _, _ = content.partition("\n---\n")
    return role_section


def _rule_verbs(content: str, *, api_group: str, resource: str) -> list[str]:
    """Extract the verbs list for a ``- apiGroups: [...]\\n  resources: [...]`` rule."""
    pattern = re.compile(
        r'apiGroups:\s*\[\s*"{}"\s*\]\s*\n\s*resources:\s*\[\s*"{}"\s*\]\s*\n\s*verbs:\s*\[(.*?)\]'.format(
            re.escape(api_group), re.escape(resource)
        )
    )
    match = pattern.search(content)
    assert match is not None, f"No rule found for apiGroups={api_group!r} resources={resource!r}"
    return [verb.strip().strip('"') for verb in match.group(1).split(",")]


def test_deployments_rule_grants_create_and_delete() -> None:
    """The k8s backend creates and deletes apps/v1.Deployment objects."""
    verbs = _rule_verbs(_controller_role_source(), api_group="apps", resource="deployments")
    assert {"get", "list", "watch", "create", "delete"} <= set(verbs)


def test_services_rule_present() -> None:
    """The k8s backend creates a v1.Service alongside restart_policy=Always Deployments."""
    verbs = _rule_verbs(_controller_role_source(), api_group="", resource="services")
    assert {"get", "list", "create", "delete"} <= set(verbs)


@pytest.mark.parametrize(
    ("api_group", "resource", "required_verbs"),
    [
        ("", "pods", {"get", "list", "watch"}),
        ("", "pods/log", {"get", "list"}),
        ("batch", "jobs", {"create", "get", "list", "watch", "update", "patch", "delete"}),
        ("", "persistentvolumeclaims", {"get", "list", "create", "delete"}),
        ("", "configmaps", {"get", "list", "create", "delete"}),
    ],
)
def test_base_rules_unaffected(api_group: str, resource: str, required_verbs: set[str]) -> None:
    """Regression guard: pre-existing k8s backend RBAC rules are untouched."""
    verbs = _rule_verbs(_controller_role_source(), api_group=api_group, resource=resource)
    assert required_verbs <= set(verbs)
