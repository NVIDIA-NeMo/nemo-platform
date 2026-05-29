#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PII + secret scanner for NeMo agent telemetry.

Source of truth for the regex pass invoked by the `nemo-agents-secure` skill.
Reads one or more files (or directories, recursively), runs anchored regexes
for common PII and API-key formats, applies false-positive guards, and emits
a single JSON object on stdout summarizing the scan.

Stdlib only — no third-party deps. Runs on any python3 >= 3.8.

Usage:
    pii_scan.py PATH [PATH ...]
    cat trace.jsonl | pii_scan.py -            # read stdin

Output shape:
    {
      "scanned_files": ["/abs/path/file.jsonl", ...],
      "scanned_bytes": 12345678,
      "counts_by_type": {"email": 3, "openai_api_key": 1, ...},
      "hits": [
        {
          "type": "email",
          "masked_preview": "j***@e****.com",
          "file": "/abs/path/file.jsonl",
          "line": 42,
          "column": 17,
          "context": "...±80 char window..."
        },
        ...
      ]
    }

Each hit is verified against ±80 chars of surrounding context using per-type
guards (e.g. drop SSN-shaped digit runs that are part of a longer numeric
id, drop credit-card-shaped runs that fail Luhn). Patterns are deliberately
prefix-anchored where possible to keep false-positive rate low.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

CONTEXT_WINDOW = 80


# --------------------------------------------------------------------------- #
# Masking helpers
# --------------------------------------------------------------------------- #


def _mask_middle(value: str, keep: int = 2) -> str:
    """Mask the middle of `value`, keeping `keep` chars on each side."""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern[str]
    guard: Callable[[str, re.Match[str]], bool] | None = None
    mask: Callable[[str], str] = _mask_middle


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not domain:
        return _mask_middle(value)
    domain_name, _, tld = domain.rpartition(".")
    masked_local = _mask_middle(local, keep=1) if local else ""
    masked_domain = _mask_middle(domain_name, keep=1) if domain_name else ""
    return f"{masked_local}@{masked_domain}.{tld}" if tld else f"{masked_local}@{_mask_middle(domain, keep=1)}"


def _mask_prefix(value: str, prefix_len: int) -> str:
    """Keep a prefix (e.g. 'ghp_', 'sk-ant-') verbatim, mask the rest."""
    if len(value) <= prefix_len:
        return value
    return value[:prefix_len] + _mask_middle(value[prefix_len:], keep=2)


# --------------------------------------------------------------------------- #
# False-positive guards
# --------------------------------------------------------------------------- #


_ID_KEY_RE = re.compile(
    r"(request_id|req_id|trace_id|span_id|run_id|job_id|task_id|build_id|"
    r"correlation_id|x-request-id|uuid)",
    re.IGNORECASE,
)
_ISO_TIMESTAMP_NEAR = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def _luhn_ok(digits: str) -> bool:
    s = 0
    alt = False
    for ch in reversed(digits):
        if not ch.isdigit():
            continue
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0 and len(digits) >= 13


def _guard_ssn(context: str, match: re.Match[str]) -> bool:
    # Drop if the match sits inside a wider digit run (e.g. embedded in a
    # request id or Unix epoch).
    start, end = match.span()
    before = context[max(0, start - 1) : start]
    after = context[end : end + 1]
    if before.isdigit() or after.isdigit():
        return False
    if _ID_KEY_RE.search(context):
        return False
    return True


def _guard_phone(context: str, match: re.Match[str]) -> bool:
    if _ID_KEY_RE.search(context):
        return False
    if _ISO_TIMESTAMP_NEAR.search(context):
        return False
    # Drop if the run is embedded in a longer digit run (Unix epoch shape).
    start, end = match.span()
    before = context[max(0, start - 1) : start]
    after = context[end : end + 1]
    if before.isdigit() or after.isdigit():
        return False
    return True


def _guard_credit_card(context: str, match: re.Match[str]) -> bool:
    digits = re.sub(r"\D", "", match.group(0))
    return _luhn_ok(digits)


# --------------------------------------------------------------------------- #
# Pattern catalog
# --------------------------------------------------------------------------- #


PATTERNS: tuple[PatternSpec, ...] = (
    # ---- PII -------------------------------------------------------------
    PatternSpec(
        name="email",
        regex=re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        mask=_mask_email,
    ),
    PatternSpec(
        name="ssn",
        regex=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        guard=_guard_ssn,
    ),
    PatternSpec(
        name="phone",
        regex=re.compile(r"\b(?:\+1[\s\-.])?\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}\b"),
        guard=_guard_phone,
    ),
    PatternSpec(
        name="credit_card",
        regex=re.compile(r"\b(?:\d{4}[\s\-]){3}\d{4}\b|\b\d{15,16}\b"),
        guard=_guard_credit_card,
    ),
    # ---- Cloud / cluster credentials -------------------------------------
    PatternSpec(
        name="aws_access_key_id",
        regex=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        mask=lambda s: _mask_prefix(s, 4),
    ),
    PatternSpec(
        name="google_api_key",
        regex=re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        mask=lambda s: _mask_prefix(s, 4),
    ),
    # ---- Source-control / CI tokens --------------------------------------
    PatternSpec(
        name="github_pat_classic",
        regex=re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        mask=lambda s: _mask_prefix(s, 4),
    ),
    PatternSpec(
        name="github_pat_fine_grained",
        regex=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
        mask=lambda s: _mask_prefix(s, 11),
    ),
    PatternSpec(
        name="github_oauth_token",
        regex=re.compile(r"\b(?:gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"),
        mask=lambda s: _mask_prefix(s, 4),
    ),
    PatternSpec(
        name="gitlab_pat",
        regex=re.compile(r"\bglpat-[A-Za-z0-9_\-]{20}\b"),
        mask=lambda s: _mask_prefix(s, 6),
    ),
    # ---- Model-provider API keys -----------------------------------------
    PatternSpec(
        # Negative lookahead avoids double-matching Anthropic keys (sk-ant-…).
        name="openai_api_key",
        regex=re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_\-]{20,}\b"),
        mask=lambda s: _mask_prefix(s, 8 if s.startswith("sk-proj-") else 3),
    ),
    PatternSpec(
        name="anthropic_api_key",
        regex=re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{32,}\b"),
        mask=lambda s: _mask_prefix(s, 7),
    ),
    PatternSpec(
        name="huggingface_token",
        regex=re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"),
        mask=lambda s: _mask_prefix(s, 3),
    ),
    PatternSpec(
        name="nvidia_api_key",
        regex=re.compile(r"\bnvapi-[A-Za-z0-9_\-]{60,}\b"),
        mask=lambda s: _mask_prefix(s, 6),
    ),
    # ---- Messaging / payments --------------------------------------------
    PatternSpec(
        name="slack_token",
        regex=re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        mask=lambda s: _mask_prefix(s, 5),
    ),
    PatternSpec(
        name="stripe_secret_key",
        regex=re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{24,}\b"),
        mask=lambda s: _mask_prefix(s, 8),
    ),
    # ---- Generic ---------------------------------------------------------
    PatternSpec(
        name="jwt",
        regex=re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        mask=lambda s: _mask_prefix(s, 4),
    ),
    PatternSpec(
        name="private_key_block",
        regex=re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----"),
        mask=lambda s: s,  # the marker itself isn't sensitive; keep verbatim
    ),
)


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #


@dataclass
class ScanResult:
    scanned_files: list[str] = field(default_factory=list)
    scanned_bytes: int = 0
    hits: list[dict] = field(default_factory=list)
    counts_by_type: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "scanned_files": self.scanned_files,
                "scanned_bytes": self.scanned_bytes,
                "counts_by_type": self.counts_by_type,
                "hits": self.hits,
            },
            indent=2,
            sort_keys=True,
        )


def _iter_files(paths: list[str]) -> Iterator[Path]:
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            print(f"warning: {p} does not exist, skipping", file=sys.stderr)
            continue
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file():
                    yield sub


def _scan_text(text: str, source: str, result: ScanResult, seen: set[tuple]) -> None:
    # Build a line-offset map once so we can report 1-indexed line + column
    # without re-walking the buffer for each match.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def locate(offset: int) -> tuple[int, int]:
        # binary search the line for `offset`
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, offset - line_starts[lo] + 1

    for spec in PATTERNS:
        for match in spec.regex.finditer(text):
            start, end = match.span()
            ctx_start = max(0, start - CONTEXT_WINDOW)
            ctx_end = min(len(text), end + CONTEXT_WINDOW)
            context = text[ctx_start:ctx_end]
            local_match = re.search(re.escape(match.group(0)), context)
            if spec.guard and local_match and not spec.guard(context, local_match):
                continue

            line, column = locate(start)
            value = match.group(0)
            key = (spec.name, value, source, line)
            if key in seen:
                continue
            seen.add(key)

            result.hits.append(
                {
                    "type": spec.name,
                    "masked_preview": spec.mask(value),
                    "file": source,
                    "line": line,
                    "column": column,
                    "context": context.replace("\n", " ")[: CONTEXT_WINDOW * 2 + len(value)],
                }
            )
            result.counts_by_type[spec.name] = result.counts_by_type.get(spec.name, 0) + 1


def scan_paths(paths: list[str], stdin_label: str = "<stdin>") -> ScanResult:
    result = ScanResult()
    seen: set[tuple] = set()

    if paths == ["-"]:
        text = sys.stdin.read()
        result.scanned_files.append(stdin_label)
        result.scanned_bytes += len(text.encode("utf-8", errors="replace"))
        _scan_text(text, stdin_label, result, seen)
        return result

    for path in _iter_files(paths):
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            continue
        text = data.decode("utf-8", errors="replace")
        abs_path = str(path.resolve())
        result.scanned_files.append(abs_path)
        result.scanned_bytes += len(data)
        _scan_text(text, abs_path, result, seen)

    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan files for PII and API-key formats. Emits a JSON summary to "
            "stdout. Use a single '-' to read from stdin."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to scan, or '-' to read stdin.",
    )
    args = parser.parse_args(argv)

    result = scan_paths(args.paths)
    print(result.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
