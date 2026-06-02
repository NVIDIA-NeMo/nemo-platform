#!/usr/bin/env -S uv run --script
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# /// script
# dependencies = [
#   "typer",
#   "gitpython",
# ]
# ///


"""
Copyright header fixer for NeMo-Platform

Scans source files and adds SPDX copyright headers where missing.
"""

import os
import re
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import typer
from git import InvalidGitRepositoryError, Repo

app = typer.Typer(name="copyright-fixer", help="Copyright fixer tool for NeMo-Platform.", no_args_is_help=True)

# --- constants ---

_CURRENT_YEAR = datetime.now().year

_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css"})

_COPYRIGHT_IGNORE_FILE = ".copyrightignore"

# Comment-style headers by file type
_HASH_HEADER = (
    f"# SPDX-FileCopyrightText: Copyright (c) 2025-{_CURRENT_YEAR} NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n"
    "# SPDX-License-Identifier: Apache-2.0\n"
)

_SLASH_HEADER = (
    f"// SPDX-FileCopyrightText: Copyright (c) 2025-{_CURRENT_YEAR} NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n"
    "// SPDX-License-Identifier: Apache-2.0\n"
)

_CSS_HEADER = (
    f"/* SPDX-FileCopyrightText: Copyright (c) 2025-{_CURRENT_YEAR} NVIDIA CORPORATION & AFFILIATES. All rights reserved. */\n"
    "/* SPDX-License-Identifier: Apache-2.0 */\n"
)

_HTML_HEADER = (
    f"<!-- SPDX-FileCopyrightText: Copyright (c) 2025-{_CURRENT_YEAR} NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->\n"
    "<!-- SPDX-License-Identifier: Apache-2.0 -->\n"
)

# Cheap substring checks — no regex needed
_HEADER_MARKERS = (
    "SPDX-FileCopyrightText",
    "SPDX-License-Identifier",
    "Copyright (c)",
    "Copyright (C)",
)

_PROPRIETARY_LICENSE = "LicenseRef-NvidiaProprietary"
_CORRECT_LICENSE = "Apache-2.0"

# --- SPDX header regexes ---
#
# "Correct" regexes match the exact NVIDIA SPDX format (any valid year/range,
# Apache-2.0 only).  Used for validation (_has_correct_spdx_header).
#
# "Any" regexes match any two-line SPDX block regardless of content.
# Used for stripping old headers during replacement (_fix_non_spdx_header).

_NVIDIA_COPYRIGHT = r"Copyright \(c\) \d{4}(?:-\d{4})?,? ?NVIDIA CORPORATION & AFFILIATES\. All rights reserved\."
_APACHE_2 = r"Apache-2\.0"

# -- correct header (per comment style) --

_CORRECT_SPDX_HASH_RE = re.compile(
    rf"# SPDX-FileCopyrightText: {_NVIDIA_COPYRIGHT}\n"
    rf"# SPDX-License-Identifier: {_APACHE_2}\n"
)
_CORRECT_SPDX_SLASH_RE = re.compile(
    rf"// SPDX-FileCopyrightText: {_NVIDIA_COPYRIGHT}\n"
    rf"// SPDX-License-Identifier: {_APACHE_2}\n"
)
_CORRECT_SPDX_CSS_RE = re.compile(
    rf"/\* SPDX-FileCopyrightText: {_NVIDIA_COPYRIGHT} \*/\n"
    rf"/\* SPDX-License-Identifier: {_APACHE_2} \*/\n"
)
_CORRECT_SPDX_BLOCK_RE = re.compile(
    rf" \* SPDX-FileCopyrightText: {_NVIDIA_COPYRIGHT}\n"
    rf" \* SPDX-License-Identifier: {_APACHE_2}\n"
)

_CORRECT_SPDX_PATTERNS = (
    _CORRECT_SPDX_HASH_RE,
    _CORRECT_SPDX_SLASH_RE,
    _CORRECT_SPDX_CSS_RE,
    _CORRECT_SPDX_BLOCK_RE,
)

# -- any SPDX block (per comment style, for replacement) --

_ANY_SPDX_HASH_RE = re.compile(
    r"# SPDX-FileCopyrightText:[^\n]*\n"
    r"# SPDX-License-Identifier:[^\n]*\n"
)
_ANY_SPDX_SLASH_RE = re.compile(
    r"// SPDX-FileCopyrightText:[^\n]*\n"
    r"// SPDX-License-Identifier:[^\n]*\n"
)
_ANY_SPDX_CSS_RE = re.compile(
    r"/\* SPDX-FileCopyrightText:[^\n]* \*/\n"
    r"/\* SPDX-License-Identifier:[^\n]* \*/\n"
)
_ANY_SPDX_BLOCK_RE = re.compile(
    r" \* SPDX-FileCopyrightText:[^\n]*\n"
    r" \* SPDX-License-Identifier:[^\n]*\n"
)

# -- legacy / proprietary patterns (not SPDX at all) --

_LEGACY_APACHE_HASH_RE = re.compile(
    r"# Copyright \(c\) \d{4},?\s*NVIDIA CORPORATION\.?\s*All rights reserved\.\n"
    r"(?:#[^\n]*\n)*?"
    r"# limitations under the License\.\n"
)
_LEGACY_APACHE_SLASH_RE = re.compile(
    r"// Copyright \(c\) \d{4},?\s*NVIDIA CORPORATION\.?\s*All rights reserved\.\n"
    r"(?://[^\n]*\n)*?"
    r"// limitations under the License\.\n"
)
_PROPRIETARY_BLOCK_RE = re.compile(
    r"/\*\n"
    r"(?: \*[^\n]*\n)*?"
    r" \* SPDX-License-Identifier: LicenseRef-NvidiaProprietary\n"
    r"(?: \*[^\n]*\n)*?"
    r" \*/\n"
)

# Patterns used to strip non-compliant headers (order: specific first, then generic)
_NON_SPDX_PATTERNS = (
    _PROPRIETARY_BLOCK_RE,
    _LEGACY_APACHE_HASH_RE,
    _LEGACY_APACHE_SLASH_RE,
    _ANY_SPDX_HASH_RE,
    _ANY_SPDX_SLASH_RE,
    _ANY_SPDX_CSS_RE,
    _ANY_SPDX_BLOCK_RE,
)


def _matches_path_filter(relpath: str, patterns: list[str]) -> bool:
    """Return True if *relpath* matches any of the given path patterns.

    Patterns are matched as prefixes first (e.g. ``services/evaluator``
    matches ``services/evaluator/src/foo.py``).  If a pattern contains
    glob characters it falls back to fnmatch on the full relative path.
    """
    for pat in patterns:
        pat = pat.strip("/")
        if pat in ("", "."):
            return True
        if "*" in pat or "?" in pat or "[" in pat:
            if fnmatch(relpath, pat) or fnmatch(relpath, pat + "/*"):
                return True
        else:
            if relpath == pat or relpath.startswith(pat + "/"):
                return True
    return False


# --- ignore helpers ---


def _get_repo(start: str) -> Repo | None:
    """Discover the git repository containing *start*."""
    try:
        return Repo(start, search_parent_directories=True)
    except InvalidGitRepositoryError:
        return None


def _load_copyright_excludes(repo_root: str | None) -> list[str]:
    """Load exclude patterns from .copyrightignore at the repo root."""
    if repo_root is None:
        return []
    ignore_path = os.path.join(repo_root, _COPYRIGHT_IGNORE_FILE)
    if not os.path.isfile(ignore_path):
        return []
    with open(ignore_path, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


def _pat_matches(relpath: str, p: Path, pat: str) -> bool:
    """Return True if *pat* matches *relpath*.

    Pattern semantics (gitignore-like):
      - Trailing ``/`` → directory prefix match anchored at the repo root.
      - Contains ``/`` (no trailing) → fnmatch from repo root.
      - Bare name → fnmatch on the file's basename.
    """
    if pat.endswith("/"):
        prefix = pat.rstrip("/")
        return relpath == prefix or relpath.startswith(prefix + "/")
    if "/" in pat:
        return fnmatch(relpath, pat)
    return fnmatch(p.name, pat)


def _is_copyright_excluded(relpath: str, patterns: list[str]) -> bool:
    """Return True if the file should be excluded per .copyrightignore.

    Supports gitignore-style ``!`` negation: a pattern starting with ``!``
    un-excludes a previously excluded path.  Patterns are processed in
    order — **last match wins**.
    """
    excluded = False
    p = Path(relpath)
    for raw_pat in patterns:
        negate = raw_pat.startswith("!")
        pat = raw_pat[1:] if negate else raw_pat
        if _pat_matches(relpath, p, pat):
            excluded = not negate
    return excluded


# --- core helpers ---


def _has_header(head: str) -> bool:
    """Check the first ~512 bytes for any copyright marker."""
    for marker in _HEADER_MARKERS:
        if marker in head:
            return True
    return False


def _has_correct_spdx_header(head: str) -> bool:
    """Return True if the head contains a correct NVIDIA SPDX copyright header."""
    return any(p.search(head) for p in _CORRECT_SPDX_PATTERNS)


def _has_non_spdx_header(filepath: str) -> bool:
    """Return True if the file has a copyright header that is not the correct SPDX format."""
    head = _read_head(filepath)
    if not head:
        return False
    return _has_header(head) and not _has_correct_spdx_header(head)


def _read_head(path: str, nbytes: int = 512) -> str:
    """Read the first *nbytes* of a file (fast, no full-file read)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(nbytes)
    except OSError:
        return ""


def _collect_files_from_dir(root: str) -> list[str]:
    """Collect files under *root* matching _EXTENSIONS, respecting .gitignore and .copyrightignore."""
    repo = _get_repo(root)

    if repo is not None:
        repo_root = str(repo.working_tree_dir)
        copyright_excludes = _load_copyright_excludes(repo_root)
        raw = repo.git.ls_files("--cached", "--others", "--exclude-standard", "-z", "--", root)
        git_files = [f for f in raw.split("\0") if f]
        target_files = [os.path.join(repo_root, f) for f in git_files if os.path.splitext(f)[1] in _EXTENSIONS]
    else:
        copyright_excludes = _load_copyright_excludes(None)
        target_files = []
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if os.path.splitext(fname)[1] in _EXTENSIONS:
                    target_files.append(os.path.join(dirpath, fname))

    target_files = [f for f in target_files if not _is_copyright_excluded(os.path.relpath(f, root), copyright_excludes)]

    return target_files


_SLASH_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})


def _get_header_for_ext(ext: str) -> str:
    """Return the appropriate copyright header for the given file extension."""
    if ext in _SLASH_EXTENSIONS:
        return _SLASH_HEADER + "\n"
    if ext == ".css":
        return _CSS_HEADER + "\n"
    if ext in {".py", ".sh", ".yaml", ".yml"}:
        return _HASH_HEADER + "\n"
    if ext == ".md":
        return _HTML_HEADER + "\n"
    return _HASH_HEADER + "\n"


def _get_header_for_file(filepath: str, content: str) -> str:
    """Return the appropriate copyright header, considering both extension and shebang."""
    ext = os.path.splitext(filepath)[1]

    # Check shebang for tsx/node — these files need // style comments
    if content.startswith("#!"):
        shebang_end = content.find("\n")
        shebang = content[: shebang_end if shebang_end != -1 else len(content)]
        if "tsx" in shebang or "node" in shebang or "bun" in shebang:
            return _SLASH_HEADER + "\n"

    return _get_header_for_ext(ext)


def _needs_style_fix(filepath: str) -> bool:
    """Return True if the file has a copyright header with wrong comment style."""
    head = _read_head(filepath)
    if not _has_header(head):
        return False
    expected = _get_header_for_file(filepath, head)
    return "# SPDX-FileCopyrightText" in head and expected.startswith("//")


def _has_proprietary_license(head: str) -> bool:
    """Return True if the file uses the disallowed NvidiaProprietary license."""
    return _PROPRIETARY_LICENSE in head


def _fix_proprietary_license(filepath: str) -> bool:
    """Replace LicenseRef-NvidiaProprietary with Apache-2.0. Returns True if modified."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return False

    if _PROPRIETARY_LICENSE not in content:
        return False

    new_content = content.replace(_PROPRIETARY_LICENSE, _CORRECT_LICENSE)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _fix_header_style(filepath: str) -> bool:
    """Fix wrong comment style on existing headers. Returns True if modified."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return False

    if not _has_header(content[:512]):
        return False

    expected_header = _get_header_for_file(filepath, content)
    # Check if the file uses #-style when it should use //-style (or vice versa)
    has_hash = "# SPDX-FileCopyrightText" in content[:512]
    needs_slash = expected_header.startswith("//")

    if has_hash and needs_slash:
        new_content = content.replace("# SPDX-FileCopyrightText", "// SPDX-FileCopyrightText", 1).replace(
            "# SPDX-License-Identifier", "// SPDX-License-Identifier", 1
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    return False


def _fix_non_spdx_header(filepath: str) -> bool:
    """Replace legacy / non-standard copyright headers with correct SPDX. Returns True if modified."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return False

    head = content[:1024]
    if not _has_header(head) or _has_correct_spdx_header(head):
        return False

    # Only remove a legacy header that starts exactly where the file header
    # should be — right after an optional shebang line and leading blank lines.
    # We search `head` (not the full content) and require the match to begin at
    # header_start so we never accidentally delete a copyright-like block that
    # appears later in the file body.  The match offsets are valid indices into
    # content because head == content[:1024].
    header_start = 0
    if content.startswith("#!"):
        nl = content.find("\n")
        header_start = (nl + 1) if nl != -1 else len(content)
    while header_start < len(head) and head[header_start] == "\n":
        header_start += 1

    new_content = content
    for pattern in _NON_SPDX_PATTERNS:
        match = pattern.search(head, pos=header_start)
        if match and match.start() == header_start:
            new_content = content[: match.start()] + content[match.end() :]
            break
    else:
        return False

    # Strip leading blank lines left by header removal, then prepend correct header
    remaining = new_content.lstrip("\n")
    header = _get_header_for_file(filepath, remaining)
    if remaining.startswith("#!"):
        nl = remaining.find("\n")
        pos = nl + 1 if nl != -1 else len(remaining)
        new_content = remaining[:pos] + header + remaining[pos:]
    else:
        new_content = header + remaining

    # Collapse runs of 3+ blank lines to 2
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)

    if new_content == content:
        return False

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _add_header(filepath: str) -> bool:
    """Add the copyright header to *filepath*. Returns True if modified."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return False

    if not content.strip():
        return False

    if _has_header(content[:512]):
        return False

    header = _get_header_for_file(filepath, content)

    if content.startswith("#!"):
        nl = content.find("\n")
        newline_pos = nl + 1 if nl != -1 else len(content)
        new_content = content[:newline_pos] + header + content[newline_pos:]
    elif os.path.splitext(filepath)[1] == ".md" and (content.startswith("---\n") or content.startswith("---\r\n")):
        # Insert copyright as YAML comments right after opening ---
        sep = "---\r\n" if content.startswith("---\r\n") else "---\n"
        new_content = sep + _HASH_HEADER + content[len(sep) :]
    else:
        new_content = header + content

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def _resolve_targets(paths: list[Path]) -> tuple[list[str], str | None]:
    """Return (file_list, display_root)."""
    if len(paths) == 1 and paths[0].is_dir():
        root = str(paths[0].resolve())
        return _collect_files_from_dir(root), root

    repo = _get_repo(str(paths[0].resolve()))
    repo_root = str(repo.working_tree_dir) if repo else None
    copyright_excludes = _load_copyright_excludes(repo_root)

    files = [
        str(p.resolve())
        for p in paths
        if p.is_file()
        and os.path.splitext(str(p))[1] in _EXTENSIONS
        and not _is_copyright_excluded(str(p), copyright_excludes)
    ]
    return files, None


# --- CLI ---


@app.command()
def update_license_headers(
    paths: list[Path] = typer.Argument(
        default=None,
        help="Directory to scan or individual files to process. Defaults to current directory.",
    ),
    check: bool = typer.Option(False, "--check", help="Check only, don't modify files. Exit 1 if headers are missing."),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show files that would be updated, without modifying anything."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Fix all non-compliant headers (proprietary, legacy, non-standard SPDX)."
    ),
    fix_style: bool = typer.Option(
        False, "--fix-style", help="Fix headers that use the wrong comment style (e.g. # instead of // in TS/JS files)."
    ),
    include: list[str] = typer.Option(
        None, "--include", "-i", help="Only process files under these directories/patterns (relative to root)."
    ),
    exclude: list[str] = typer.Option(
        None, "--exclude", "-e", help="Skip files under these directories/patterns (relative to root)."
    ),
) -> None:
    """Add SPDX copyright headers to files missing them.

    Accepts a single directory (scans recursively) or a list of individual
    files.  When no argument is provided, scans the current directory.

    Use --fix to replace non-compliant headers (proprietary licenses,
    old-style Apache blocks, non-standard SPDX) with the correct SPDX
    format.

    Use --fix-style to also correct headers that use the wrong comment
    style (e.g. ``# SPDX-...`` in TypeScript files instead of ``// SPDX-...``).

    Use --include / --exclude to selectively target directories so you
    don't end up with a monster commit::

        # Only process two directories
        ./script/copyright_fixer.py . --include services/evaluator --include packages/models

        # Process everything except generated SDK code
        ./script/copyright_fixer.py . --exclude packages/nemo_platform
    """
    if not paths:
        paths = [Path(".")]

    for p in paths:
        if not p.exists():
            typer.echo(f"Error: {p} does not exist", err=True)
            raise typer.Exit(code=1)

    files, root = _resolve_targets(paths)

    # Apply --include / --exclude filters (include takes priority over exclude)
    if include or exclude:
        base = root or os.getcwd()
        filtered = []
        for f in files:
            rel = os.path.relpath(f, base)
            if include and _matches_path_filter(rel, include):
                filtered.append(f)
            elif exclude and _matches_path_filter(rel, exclude):
                continue
            elif include:
                continue
            else:
                filtered.append(f)
        files = filtered

    def _rel(filepath: str) -> str:
        if root:
            return os.path.relpath(filepath, root)
        return filepath

    # Classify files by issue type
    proprietary = [f for f in files if _has_proprietary_license(_read_head(f))]
    non_spdx = [f for f in files if _has_non_spdx_header(f) and f not in proprietary]
    missing = [f for f in files if _read_head(f).strip() and not _has_header(_read_head(f))]

    if check or dry_run:
        has_issues = False
        if missing:
            has_issues = True
            typer.echo(f"Found {len(missing)} file(s) missing copyright headers:")
            for f in missing:
                typer.echo(f"  - {_rel(f)}")
        if proprietary:
            has_issues = True
            typer.echo(
                f"Error: {len(proprietary)} file(s) use disallowed proprietary license — all files must be open source (Apache-2.0):"
            )
            for f in proprietary:
                typer.echo(f"  ! {_rel(f)}")
        if non_spdx:
            has_issues = True
            typer.echo(f"Error: {len(non_spdx)} file(s) have non-standard copyright headers (expected SPDX format):")
            for f in non_spdx:
                typer.echo(f"  ~ {_rel(f)}")
        if has_issues:
            if proprietary or non_spdx:
                typer.echo("  Run with --fix to replace non-compliant headers with correct SPDX format.")
            if check:
                raise typer.Exit(code=1)
        else:
            typer.echo(f"All {len(files)} file(s) have correct copyright headers.")
    else:
        updated = 0

        # Fix non-compliant headers (proprietary + legacy/non-standard) when --fix is set
        if proprietary or non_spdx:
            if fix:
                for filepath in proprietary + non_spdx:
                    if _fix_non_spdx_header(filepath):
                        updated += 1
                        typer.echo(f"  ~ {_rel(filepath)} (header replaced with SPDX)")
                    elif filepath in proprietary and _fix_proprietary_license(filepath):
                        updated += 1
                        typer.echo(f"  ! {_rel(filepath)} (fixed: {_PROPRIETARY_LICENSE} -> {_CORRECT_LICENSE})")
            else:
                if proprietary:
                    typer.echo(
                        f"Error: {len(proprietary)} file(s) use disallowed proprietary license — all files must be open source (Apache-2.0):",
                        err=True,
                    )
                    for f in proprietary:
                        typer.echo(f"  ! {_rel(f)}", err=True)
                if non_spdx:
                    typer.echo(
                        f"Error: {len(non_spdx)} file(s) have non-standard copyright headers (expected SPDX format):",
                        err=True,
                    )
                    for f in non_spdx:
                        typer.echo(f"  ~ {_rel(f)}", err=True)
                typer.echo("  Run with --fix to replace non-compliant headers with correct SPDX format.", err=True)
                raise typer.Exit(code=1)

        for filepath in files:
            if _add_header(filepath):
                updated += 1
                typer.echo(f"  + {_rel(filepath)}")
            elif fix_style and _fix_header_style(filepath):
                updated += 1
                typer.echo(f"  ~ {_rel(filepath)}")
        typer.echo(f"  Processed {len(files)} files, updated {updated}")
        if updated:
            typer.echo(f"Run 'git diff' to review {updated} changed file(s).")


if __name__ == "__main__":
    app()
