#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render ``audit.md`` from ETHOS.md metadata and reviewed audit items."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _markdown import BEGIN_MARKER, END_MARKER  # noqa: E402
from _schema import AUDIT_SCHEMA, AuditEnvironmentError, AuditSpecError, validate_audit_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ethos", type=Path, required=True, help="source ETHOS.md")
    parser.add_argument("--items", type=Path, required=True, help="YAML file containing audit items")
    parser.add_argument("--out", type=Path, required=True, help="audit.md file to write")
    parser.add_argument("--agent", help="agent name; defaults to ETHOS.md front matter name or file stem")
    parser.add_argument("--status", choices=("draft", "approved"), default="draft")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    args = parser.parse_args(argv)

    if args.out.exists() and not args.force:
        print(f"{args.out} already exists; pass --force to overwrite", file=sys.stderr)
        return 1
    try:
        yaml = _load_yaml()
        ethos_bytes = args.ethos.read_bytes()
        ethos_text = ethos_bytes.decode("utf-8")
        items = _load_items_file(args.items, yaml)
        agent = args.agent or _agent_name(ethos_text, args.ethos, yaml)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        spec = validate_audit_spec(
            {
                "schema": AUDIT_SCHEMA,
                "agent": agent,
                "sources": [
                    {
                        "name": "ethos",
                        "path": _source_path(args.ethos, args.out),
                        "sha256": f"sha256:{hashlib.sha256(ethos_bytes).hexdigest()}",
                    }
                ],
                "status": args.status,
                "items": items,
            },
            audit_path=args.out,
        )
    except AuditEnvironmentError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, AuditSpecError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    rendered = _render(spec, yaml)
    args.out.write_text(rendered, encoding="utf-8")
    print(args.out)
    return 0


def _load_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise AuditEnvironmentError("PyYAML is required to generate audit specs") from exc
    return yaml


def _load_items_file(path: Path, yaml: Any) -> list[Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AuditSpecError(f"audit items YAML does not parse: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        raise AuditSpecError("audit items file must be a list or a mapping with an items list")
    return payload


def _agent_name(ethos_text: str, ethos_path: Path, yaml: Any) -> str:
    if ethos_text.startswith("---\n"):
        parts = ethos_text.split("---\n", 2)
        if len(parts) == 3:
            try:
                payload = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as exc:
                raise AuditSpecError(f"ETHOS.md frontmatter YAML does not parse: {exc}") from exc
            if isinstance(payload, dict):
                name = payload.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return ethos_path.stem.lower()


def _source_path(source: Path, out: Path) -> str:
    return Path(os.path.relpath(source.resolve(), start=out.parent.resolve())).as_posix()


def _render(spec: dict[str, Any], yaml: Any) -> str:
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    yaml_body = yaml.safe_dump(spec, sort_keys=False, allow_unicode=False)
    source_path = spec["sources"][0]["path"]
    return (
        f"# Audit: {spec['agent']}\n\n"
        f"Generated from `{source_path}` at {created}.\n\n"
        "This file defines the finite coverage denominator generated from `ETHOS.md`.\n"
        "Generated and hand-edited content is allowed outside the marked block; scripts\n"
        "validate only the block between the markers.\n\n"
        f"{BEGIN_MARKER}\n"
        "```yaml\n"
        f"{yaml_body}"
        "```\n"
        f"{END_MARKER}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
