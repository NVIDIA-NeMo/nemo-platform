# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mapping between Harbor package references and NeMo entity names.

Harbor addresses a package as ``org/short-name``. NeMo addresses a task as
``workspace/name``, where *workspace* is a tenancy boundary with its own lifecycle and
authorization, not a cheap self-serve namespace like a Harbor org. Creating one per org on
publish would make ``harbor publish`` a tenancy operation, so the org is folded into the
entity name instead: ``nvidia/my-task`` becomes ``nvidia.my-task`` in a single workspace.

The cost is that the org is a naming convention rather than an enforced boundary. Anyone who
can publish to the workspace can publish under any org prefix.
"""

from __future__ import annotations

import re

#: The entity *store's* name rule, which is stricter than the evaluator route's own
#: ``^[\w\-\.]+$``/255. A name that passes the route can still be rejected by the store, so this
#: is the one worth validating against — it is the one that actually fails, and it fails late.
_ENTITY_NAME_PATTERN = re.compile(r"^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}$")

#: Names may not end with a hyphen (the store's rule carries a trailing negative lookbehind).
_TRAILING_HYPHEN = re.compile(r"-$")

MAX_ENTITY_NAME_LENGTH = 63


class NameMappingError(ValueError):
    """A Harbor reference cannot be represented as a NeMo entity name.

    Deliberately a ``ValueError``: on the read path this is indistinguishable from "no such
    package", because a reference NeMo could never have stored is a reference NeMo does not
    have. The publish path catches it and re-raises as a backend error, where the caller can
    act on it.
    """


def to_entity_name(org: str, name: str) -> str:
    """Map ``org``/``name`` to the NeMo entity name that holds it.

    Raises :class:`NameMappingError` when the result could not be stored. Validating here
    rather than letting the store reject it turns a late, opaque 422 into a message that names
    the actual constraint.
    """
    if "." in org:
        # The decode splits on the first dot, so a dotted org would be ambiguous with a dotted
        # package name. Rejecting is better than a silent mis-split on the way back out.
        raise NameMappingError(
            f"Harbor org {org!r} contains a '.', which cannot be represented: the org and "
            f"package name are joined with '.' and split on the first one."
        )

    entity_name = f"{org}.{name}"

    if len(entity_name) > MAX_ENTITY_NAME_LENGTH:
        raise NameMappingError(
            f"{org}/{name} maps to {entity_name!r} ({len(entity_name)} chars), over the "
            f"{MAX_ENTITY_NAME_LENGTH}-character entity-name limit."
        )
    if not _ENTITY_NAME_PATTERN.match(entity_name) or _TRAILING_HYPHEN.search(entity_name):
        raise NameMappingError(
            f"{org}/{name} maps to {entity_name!r}, which is not a valid entity name. Names "
            f"must start with a lowercase letter, use only [a-z0-9-@.+_], contain no "
            f"consecutive hyphens, and not end with a hyphen."
        )
    return entity_name


def from_entity_name(entity_name: str) -> tuple[str, str]:
    """Recover ``(org, name)`` from a NeMo entity name.

    Splits on the *first* dot, which is why :func:`to_entity_name` refuses a dotted org: a
    package name may contain dots (``nvidia.my.task`` -> ``nvidia``, ``my.task``), but an org
    containing one would make the split ambiguous.
    """
    org, separator, name = entity_name.partition(".")
    if not separator:
        raise NameMappingError(
            f"Entity name {entity_name!r} has no '.' separating org from package name."
        )
    return org, name
