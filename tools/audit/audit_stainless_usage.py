#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit remaining Stainless and legacy generated Python SDK usage."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

Category = Literal[
    "dependency-config",
    "docs",
    "generated-artifact",
    "legacy-generated-sdk",
    "lockfile",
    "runtime-source",
    "runtime-test",
    "sdk-metadata",
    "sdk-tooling",
    "source-owned-sdk",
    "other",
]
FindingKind = Literal[
    "legacy-sdk-adapter",
    "legacy-sdk-import",
    "legacy-sdk-symbol",
    "sdk-package-dependency",
    "stainless-reference",
]

LEGACY_SDK_IMPORT_CATEGORIES: frozenset[Category] = frozenset(
    {
        "other",
        "runtime-source",
        "runtime-test",
        "sdk-tooling",
        "source-owned-sdk",
    }
)
ADJACENT_DEPENDENCY_CATEGORIES: frozenset[Category] = frozenset(
    {
        "dependency-config",
        "other",
        "runtime-source",
        "runtime-test",
        "sdk-tooling",
        "source-owned-sdk",
    }
)
ADJACENT_DEPENDENCY_KINDS: frozenset[FindingKind] = frozenset(
    {"legacy-sdk-adapter", "legacy-sdk-symbol", "sdk-package-dependency"}
)
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site-packages",
    }
)
TEXT_FILE_NAMES = frozenset(
    {
        ".dockerignore",
        ".gitignore",
        "Dockerfile",
        "Makefile",
        "NOTICE",
    }
)
DOCUMENTATION_FILE_NAMES = frozenset(
    {
        "AGENTS.md",
        "CONTRIBUTING.md",
        "README.md",
        "RELEASING.md",
        "SECURITY.md",
        "SKILL.md",
    }
)
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".cjs",
        ".css",
        ".html",
        ".ini",
        ".j2",
        ".js",
        ".json",
        ".lock",
        ".md",
        ".mdx",
        ".py",
        ".pyi",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)

STAINLESS_REFERENCE_RE = re.compile(
    r"\b[Ss]tainless\b|[Xx]-stainless|stainless-sdks|app\.stainless(?:api)?\.com|pkg\.stainless\.com"
)
SDK_PACKAGE_DEPENDENCY_RE = re.compile(r"(?<![\w-])nemo-platform-sdk(?![\w-])")
LEGACY_SDK_ADAPTER_RE = re.compile(r"\bclient_from_platform\b")
LEGACY_SDK_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:from\s+nemo_platform(?:\.[A-Za-z_][\w.]*)?\s+import\b|import\s+.*\bnemo_platform"
    r"(?:\.[A-Za-z_][\w.]*)?(?:\s+as\s+[A-Za-z_]\w*)?\b)"
)
LEGACY_SDK_SYMBOL_RE = re.compile(r"\b(?:NeMoPlatform|AsyncNeMoPlatform)\b")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: FindingKind
    category: Category
    owner: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    root: str
    scanned_files: int
    findings: tuple[Finding, ...]


def audit_repo(root: Path) -> AuditReport:
    """Return categorized Stainless and legacy SDK findings under ``root``."""

    resolved_root = root.resolve()
    findings: list[Finding] = []
    scanned_files = 0

    for file_path in iter_text_files(resolved_root):
        scanned_files += 1
        relative_path = file_path.relative_to(resolved_root)
        category = classify_path(relative_path)
        owner = owner_for_path(relative_path)
        text = read_text(file_path)
        import_lines = legacy_sdk_import_lines(file_path, text)

        for line_number, line in enumerate(text.splitlines(), start=1):
            if line_number in import_lines:
                findings.append(
                    Finding(
                        path=relative_path.as_posix(),
                        line=line_number,
                        kind="legacy-sdk-import",
                        category=category,
                        owner=owner,
                        detail=clean_detail(line),
                    )
                )
                continue

            if LEGACY_SDK_SYMBOL_RE.search(line):
                findings.append(
                    Finding(
                        path=relative_path.as_posix(),
                        line=line_number,
                        kind="legacy-sdk-symbol",
                        category=category,
                        owner=owner,
                        detail=clean_detail(line),
                    )
                )

            if LEGACY_SDK_ADAPTER_RE.search(line):
                findings.append(
                    Finding(
                        path=relative_path.as_posix(),
                        line=line_number,
                        kind="legacy-sdk-adapter",
                        category=category,
                        owner=owner,
                        detail=clean_detail(line),
                    )
                )

            if SDK_PACKAGE_DEPENDENCY_RE.search(line):
                findings.append(
                    Finding(
                        path=relative_path.as_posix(),
                        line=line_number,
                        kind="sdk-package-dependency",
                        category=category,
                        owner=owner,
                        detail=clean_detail(line),
                    )
                )

            if STAINLESS_REFERENCE_RE.search(line):
                findings.append(
                    Finding(
                        path=relative_path.as_posix(),
                        line=line_number,
                        kind="stainless-reference",
                        category=category,
                        owner=owner,
                        detail=clean_detail(line),
                    )
                )

    return AuditReport(
        root=resolved_root.as_posix(),
        scanned_files=scanned_files,
        findings=tuple(sorted(findings, key=lambda finding: (finding.path, finding.line, finding.kind))),
    )


def iter_text_files(root: Path) -> Sequence[Path]:
    files: list[Path] = []
    for directory, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(name for name in dir_names if name not in SKIP_DIR_NAMES and name != ".flox")
        directory_path = Path(directory)

        for file_name in sorted(file_names):
            path = directory_path / file_name
            relative_path = path.relative_to(root)
            if should_skip_path(relative_path):
                continue

            if path.name in TEXT_FILE_NAMES or path.suffix in TEXT_SUFFIXES:
                files.append(path)

    return sorted(files)


def should_skip_path(relative_path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or part == ".flox" for part in relative_path.parts)


def classify_path(relative_path: Path) -> Category:
    path = relative_path.as_posix()
    parts = relative_path.parts

    if relative_path.name == "uv.lock":
        return "lockfile"

    if path == "sdk/stainless.yaml":
        return "sdk-metadata"

    if path.startswith("openapi/") or path.startswith("web/packages/sdk/"):
        return "generated-artifact"

    if (
        path.startswith("sdk/python/nemo-platform/src/nemo_platform/")
        or path.startswith("sdk/python/nemo-platform/tests/")
        or path == "sdk/python/nemo-platform/pyproject.toml"
    ):
        return "legacy-generated-sdk"

    if relative_path.name in {"pyproject.toml", "package.json", "pnpm-lock.yaml"}:
        return "dependency-config"

    if path.startswith("sdk/python/overrides/") or path.startswith("sdk/python/nemo-platform/src/"):
        return "source-owned-sdk"

    if path.startswith("tools/nemo-platform-sdk-tools/") or path.startswith("script/") or path == "sdk/stainless.sh":
        return "sdk-tooling"

    if path.startswith(".github/") or path.startswith("tools/"):
        return "sdk-tooling"

    if is_documentation_path(relative_path):
        return "docs"

    if "tests" in parts or path.startswith("e2e/"):
        return "runtime-test"

    if path.startswith(("agents/", "packages/", "plugins/", "services/")):
        return "runtime-source"

    return "other"


def is_documentation_path(relative_path: Path) -> bool:
    return (
        relative_path.name in DOCUMENTATION_FILE_NAMES
        or relative_path.suffix in {".md", ".mdx"}
        or any(part in {".agents", "docs", "skills"} for part in relative_path.parts)
    )


def owner_for_path(relative_path: Path) -> str:
    path = relative_path.as_posix()
    parts = relative_path.parts

    if path == "sdk/stainless.yaml":
        return "sdk:metadata"

    if path.startswith("sdk/python/nemo-platform/src/nemo_platform/"):
        return "sdk:legacy-python"

    if path.startswith("sdk/python/overrides/"):
        return "sdk:overrides"

    if path.startswith("sdk/python/nemo-platform/"):
        return "sdk:python"

    if path.startswith("sdk/"):
        return "sdk"

    if path.startswith("services/core/") and len(parts) >= 3:
        return f"service:core/{parts[2]}"

    if path.startswith("services/") and len(parts) >= 2:
        return f"service:{parts[1]}"

    if path.startswith("plugins/") and len(parts) >= 2:
        return f"plugin:{parts[1]}"

    if path.startswith("packages/") and len(parts) >= 2:
        return f"package:{parts[1]}"

    if path.startswith("agents/") and len(parts) >= 2:
        return f"agent:{parts[1]}"

    if path.startswith("e2e/"):
        if len(parts) >= 2 and not parts[1].endswith(".py"):
            return f"e2e:{parts[1]}"
        return "e2e:root"

    if path.startswith("tests/"):
        if len(parts) >= 2 and not parts[1].endswith(".py"):
            return f"test:{parts[1]}"
        return "test:root"

    if path.startswith("tools/") and len(parts) >= 2:
        return f"tool:{parts[1]}"

    if path.startswith("script/") and len(parts) >= 2:
        return f"script:{parts[1]}"

    if path.startswith("web/packages/") and len(parts) >= 3:
        return f"web-package:{parts[2]}"

    if path.startswith(".github/"):
        return "repo:github-actions"

    if path.startswith(".agents/"):
        return "repo:agent-guidance"

    if path.startswith("docs/"):
        return "repo:docs"

    if relative_path.name == "uv.lock":
        return "repo:lockfile"

    if relative_path.name in {"pyproject.toml", "package.json", "pnpm-lock.yaml"}:
        return "repo:dependency-config"

    if relative_path.name in DOCUMENTATION_FILE_NAMES:
        return "repo:docs"

    return "repo:other"


def legacy_sdk_import_lines(file_path: Path, text: str) -> frozenset[int]:
    if file_path.suffix != ".py":
        return frozenset()

    try:
        parsed = ast.parse(text)
    except SyntaxError:
        return fallback_legacy_sdk_import_lines(text)

    lines: set[int] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_legacy_sdk_module(alias.name):
                    lines.add(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module and is_legacy_sdk_module(node.module):
                lines.add(node.lineno)

    return frozenset(lines)


def fallback_legacy_sdk_import_lines(text: str) -> frozenset[int]:
    return frozenset(
        line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
        if LEGACY_SDK_IMPORT_LINE_RE.search(line)
    )


def is_legacy_sdk_module(module_name: str) -> bool:
    return module_name == "nemo_platform" or module_name.startswith("nemo_platform.")


def read_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="ignore")


def clean_detail(line: str) -> str:
    detail = " ".join(line.strip().split())
    if len(detail) <= 160:
        return detail

    return f"{detail[:157]}..."


def legacy_sdk_import_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.category in LEGACY_SDK_IMPORT_CATEGORIES and finding.kind == "legacy-sdk-import"
    )


def adjacent_dependency_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.category in ADJACENT_DEPENDENCY_CATEGORIES and finding.kind in ADJACENT_DEPENDENCY_KINDS
    )


def json_payload(report: AuditReport) -> dict[str, object]:
    import_findings = legacy_sdk_import_findings(report.findings)
    adjacent_findings = adjacent_dependency_findings(report.findings)
    return {
        "root": report.root,
        "summary": summary_payload(report),
        "affected_paths": sorted({finding.path for finding in import_findings}),
        "legacy_sdk_import_paths": sorted({finding.path for finding in import_findings}),
        "legacy_sdk_import_owner_summary": owner_summary_payload(import_findings),
        "active_dependency_owner_summary": owner_summary_payload(import_findings),
        "adjacent_dependency_paths": sorted({finding.path for finding in adjacent_findings}),
        "adjacent_dependency_owner_summary": owner_summary_payload(adjacent_findings),
        "findings": [asdict(finding) for finding in report.findings],
    }


def summary_payload(report: AuditReport) -> dict[str, object]:
    paths_with_findings = {finding.path for finding in report.findings}
    findings_by_kind = Counter(finding.kind for finding in report.findings)
    findings_by_category = Counter(finding.category for finding in report.findings)
    import_findings = legacy_sdk_import_findings(report.findings)
    adjacent_findings = adjacent_dependency_findings(report.findings)

    return {
        "scanned_files": report.scanned_files,
        "files_with_findings": len(paths_with_findings),
        "legacy_sdk_import_files": len({finding.path for finding in import_findings}),
        "legacy_sdk_import_findings": len(import_findings),
        "legacy_sdk_import_owners": len({finding.owner for finding in import_findings}),
        "active_dependency_files": len({finding.path for finding in import_findings}),
        "active_dependency_findings": len(import_findings),
        "active_dependency_owners": len({finding.owner for finding in import_findings}),
        "adjacent_dependency_files": len({finding.path for finding in adjacent_findings}),
        "adjacent_dependency_findings": len(adjacent_findings),
        "adjacent_dependency_owners": len({finding.owner for finding in adjacent_findings}),
        "findings_by_kind": dict(sorted(findings_by_kind.items())),
        "findings_by_category": dict(sorted(findings_by_category.items())),
    }


def owner_summary_payload(findings: Sequence[Finding]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.owner].append(finding)

    payload: dict[str, dict[str, object]] = {}
    for owner, owner_findings in sorted(grouped.items()):
        payload[owner] = {
            "files": len({finding.path for finding in owner_findings}),
            "findings": len(owner_findings),
            "findings_by_kind": dict(sorted(Counter(finding.kind for finding in owner_findings).items())),
            "paths": sorted({finding.path for finding in owner_findings}),
        }

    return payload


def print_report(
    report: AuditReport,
    *,
    limit: int,
    show_adjacent: bool,
    show_docs: bool,
    show_generated: bool,
    show_lines: bool,
    show_references: bool,
) -> None:
    summary = summary_payload(report)
    import_findings = legacy_sdk_import_findings(report.findings)
    print("Legacy Python SDK import audit")
    print(f"  Scanned files: {summary['scanned_files']}")
    print(f"  Files importing legacy SDK: {summary['legacy_sdk_import_files']}")
    print(f"  Legacy SDK import lines: {summary['legacy_sdk_import_findings']}")
    print(f"  Owners with legacy SDK imports: {summary['legacy_sdk_import_owners']}")

    print_owner_summary("\nLegacy SDK imports by owner", import_findings, limit=limit)

    if show_lines:
        print_group(
            "\nLegacy SDK import lines",
            import_findings,
            limit=limit,
            empty_text="No legacy SDK import lines found outside docs, generated artifacts, lockfiles, and metadata.",
        )

    if show_adjacent:
        adjacent_findings = adjacent_dependency_findings(report.findings)
        print("\nAdjacent dependency summary")
        print(f"  Files with adjacent findings: {summary['adjacent_dependency_files']}")
        print(f"  Adjacent findings: {summary['adjacent_dependency_findings']}")
        print(f"  Owners with adjacent findings: {summary['adjacent_dependency_owners']}")
        print_owner_summary("\nAdjacent dependency owners", adjacent_findings, limit=limit)
        if show_lines:
            print_group(
                "\nAdjacent dependency files",
                adjacent_findings,
                limit=limit,
                empty_text="No adjacent legacy SDK symbols, adapters, or package dependencies found.",
            )

    if show_references:
        print("\nAll detected findings by kind")
        print_counter(summary["findings_by_kind"])

        print("\nAll detected findings by category")
        print_counter(summary["findings_by_category"])

        print_group(
            "\nStainless-specific tooling and metadata",
            tuple(
                finding
                for finding in report.findings
                if finding.category in {"sdk-metadata", "sdk-tooling"} and finding.kind == "stainless-reference"
            ),
            limit=limit,
            empty_text="No Stainless-specific tooling or metadata references found.",
        )

    if show_generated:
        print_group(
            "\nGenerated artifact and legacy SDK findings",
            tuple(
                finding
                for finding in report.findings
                if finding.category in {"generated-artifact", "legacy-generated-sdk"}
            ),
            limit=limit,
            empty_text="No generated artifact or legacy SDK findings found.",
        )

    if show_docs:
        print_group(
            "\nDocumentation findings",
            tuple(finding for finding in report.findings if finding.category == "docs"),
            limit=limit,
            empty_text="No documentation findings found.",
        )


def print_counter(counter_obj: object) -> None:
    if not isinstance(counter_obj, dict) or not counter_obj:
        print("  none")
        return

    for key, value in counter_obj.items():
        print(f"  {key}: {value}")


def print_group(title: str, findings: Sequence[Finding], *, limit: int, empty_text: str) -> None:
    print(title)
    if not findings:
        print(f"  {empty_text}")
        return

    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.path].append(finding)

    path_count = len(grouped)
    for index, path in enumerate(sorted(grouped), start=1):
        if limit > 0 and index > limit:
            print(f"  ... {path_count - limit} more files hidden; rerun with --limit {path_count} to show all.")
            break

        path_findings = grouped[path]
        print(f"  {path} ({len(path_findings)} findings)")
        for finding in path_findings[:3]:
            print(f"    L{finding.line} {finding.kind}: {finding.detail}")
        if len(path_findings) > 3:
            print(f"    ... {len(path_findings) - 3} more findings in this file")


def print_owner_summary(title: str, findings: Sequence[Finding], *, limit: int) -> None:
    print(title)
    if not findings:
        print("  No matching owners found.")
        return

    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.owner].append(finding)

    sorted_owners = sorted(
        grouped.items(),
        key=lambda item: (-len({finding.path for finding in item[1]}), item[0]),
    )
    owner_count = len(sorted_owners)
    for index, (owner, owner_findings) in enumerate(sorted_owners, start=1):
        if limit > 0 and index > limit:
            print(f"  ... {owner_count - limit} more owners hidden; rerun with --limit {owner_count} to show all.")
            break

        paths = sorted({finding.path for finding in owner_findings})
        kind_counts = Counter(finding.kind for finding in owner_findings)
        print(f"  {owner} ({len(paths)} files, {len(owner_findings)} findings)")
        print(f"    kinds: {format_counter_inline(kind_counts)}")
        print(f"    examples: {', '.join(paths[:3])}")
        if len(paths) > 3:
            print(f"    ... {len(paths) - 3} more files for this owner")


def format_counter_inline(counter_obj: Counter[FindingKind]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in sorted(counter_obj.items()))


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root to audit. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON with all findings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum owners or files to print per report section. Defaults to 0, which shows all.",
    )
    parser.add_argument(
        "--show-docs",
        action="store_true",
        help="Print documentation findings.",
    )
    parser.add_argument(
        "--show-generated",
        action="store_true",
        help="Print generated artifact and legacy SDK findings.",
    )
    parser.add_argument(
        "--show-lines",
        action="store_true",
        help="Print per-file line details for legacy SDK imports and adjacent dependency findings.",
    )
    parser.add_argument(
        "--show-adjacent",
        action="store_true",
        help="Print non-import legacy SDK coupling such as symbols, adapters, and package dependencies.",
    )
    parser.add_argument(
        "--show-references",
        action="store_true",
        help="Print Stainless text references in tooling and metadata.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when legacy SDK import lines remain.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = audit_repo(Path(args.root))

    if args.json:
        print(json.dumps(json_payload(report), indent=2, sort_keys=True))
    else:
        print_report(
            report,
            limit=args.limit,
            show_adjacent=args.show_adjacent,
            show_docs=args.show_docs,
            show_generated=args.show_generated,
            show_lines=args.show_lines,
            show_references=args.show_references,
        )

    if args.strict and legacy_sdk_import_findings(report.findings):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
