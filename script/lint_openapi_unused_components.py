#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import sys
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

COMPONENT_SECTIONS = {
    "callbacks",
    "examples",
    "headers",
    "links",
    "parameters",
    "pathItems",
    "requestBodies",
    "responses",
    "schemas",
    "securitySchemes",
}


@dataclass(frozen=True, order=True)
class UnusedComponent:
    section: str
    name: str

    def display_name(self) -> str:
        return f"components.{self.section}.{self.name}"


def find_unused_components(spec: object) -> list[UnusedComponent]:
    if not isinstance(spec, dict):
        return []

    spec_mapping = _string_key_dict(spec)
    components = _string_key_dict_at(spec_mapping, "components")
    component_names = {
        (section, name)
        for section in COMPONENT_SECTIONS
        for name in _string_keys(_string_key_dict_at(components, section))
    }
    used_components: set[tuple[str, str]] = set()
    visited_refs: set[str] = set()
    queue: deque[object] = deque()

    queue.append(spec_mapping.get("paths", {}))
    queue.append(spec_mapping.get("webhooks", {}))
    _mark_security_requirement_list(spec_mapping.get("security", []), components, used_components, queue)

    while queue:
        current = queue.popleft()

        if isinstance(current, list):
            queue.extend(current)
            continue

        if not isinstance(current, dict):
            continue

        _mark_security_requirement_list(current.get("security", []), components, used_components, queue)
        ref = current.get("$ref")
        if isinstance(ref, str):
            component_key = _component_key_from_ref(ref)
            if component_key is not None:
                used_components.add(component_key)

            if ref not in visited_refs:
                visited_refs.add(ref)
                resolved = _resolve_internal_ref(spec_mapping, ref)
                if resolved is not None:
                    queue.append(resolved)

        queue.extend(current.values())

    return [UnusedComponent(section=section, name=name) for section, name in sorted(component_names - used_components)]


def _mark_security_requirement_list(
    security_requirements: object,
    components: Mapping[str, object],
    used_components: set[tuple[str, str]],
    queue: deque[object],
) -> None:
    if not isinstance(security_requirements, list):
        return

    security_schemes = _string_key_dict_at(components, "securitySchemes")
    for requirement in security_requirements:
        if not isinstance(requirement, dict):
            continue

        for scheme_name in requirement:
            if isinstance(scheme_name, str) and scheme_name in security_schemes:
                used_components.add(("securitySchemes", scheme_name))
                queue.append(security_schemes[scheme_name])


def _component_key_from_ref(ref: str) -> tuple[str, str] | None:
    if not ref.startswith("#/components/"):
        return None

    tokens = ref.removeprefix("#/").split("/")
    if len(tokens) < 3:
        return None

    section = _decode_pointer_token(tokens[1])
    if section not in COMPONENT_SECTIONS:
        return None

    return section, _decode_pointer_token(tokens[2])


def _resolve_internal_ref(spec: Mapping[str, object], ref: str) -> object | None:
    if not ref.startswith("#/"):
        return None

    current = spec
    for raw_token in ref.removeprefix("#/").split("/"):
        token = _decode_pointer_token(raw_token)
        if isinstance(current, dict):
            current_mapping = _string_key_dict(current)
            if token not in current_mapping:
                return None
            current = current_mapping[token]
        elif isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None

    return current


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _string_key_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    return {child_key: child_value for child_key, child_value in value.items() if isinstance(child_key, str)}


def _string_key_dict_at(mapping: Mapping[str, object], key: str) -> dict[str, object]:
    value = mapping.get(key, {})
    return _string_key_dict(value)


def _string_keys(value: dict[str, object]) -> Iterable[str]:
    return value.keys()


def _load_spec(path: Path) -> object:
    with path.open("r") as handle:
        return yaml.safe_load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail when OpenAPI components are not reachable from paths.")
    parser.add_argument("spec", nargs="+", type=Path, help="OpenAPI YAML or JSON spec path")
    args = parser.parse_args(argv)

    failed = False
    for spec_path in args.spec:
        unused_components = find_unused_components(_load_spec(spec_path))
        if not unused_components:
            continue

        failed = True
        print(f"{spec_path}: unused OpenAPI components:", file=sys.stderr)
        for component in unused_components:
            print(f"  - {component.display_name()}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
