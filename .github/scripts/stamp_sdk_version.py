# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stamp the selected SDK version before building a release wheel."""

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Literal

Cadence = Literal["nightly", "rc", "release"]
SEMVER_CORE_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


class StampError(Exception):
    """Raised when the SDK version cannot be stamped safely."""


def safe_sdk_id(sdk_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sdk_id) or sdk_id in {".", ".."}:
        raise StampError(f"selected SDK id must be a safe single path segment: {sdk_id}")
    return sdk_id


def read_assignment(path: Path, name: str) -> str:
    if not path.is_file():
        raise StampError(f"version file is missing: {path}")

    prefix = f"{name} = "
    values: list[object] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            try:
                values.append(ast.literal_eval(line.removeprefix(prefix).strip()))
            except (SyntaxError, ValueError) as error:
                raise StampError(f"{name} in {path} must be a string literal") from error

    if len(values) != 1:
        raise StampError(f"expected exactly one {name} assignment in {path}, found {len(values)}")
    if not isinstance(values[0], str) or not values[0]:
        raise StampError(f"{name} in {path} must be a non-empty string")
    return values[0]


def replace_assignment(path: Path, name: str, value: str) -> None:
    if not path.is_file():
        raise StampError(f"version file is missing: {path}")

    prefix = f"{name} = "
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise StampError(f"expected exactly one {name} assignment in {path}, found {len(matches)}")

    index = matches[0]
    newline = "\n" if lines[index].endswith("\n") else ""
    lines[index] = f'{name} = "{value}"{newline}'
    path.write_text("".join(lines), encoding="utf-8")


def resolve_sdk_version(
    cadence: Cadence,
    release_label: str,
    nightly_timestamp: str,
    shared_sdk_version_path: Path,
) -> str:
    if cadence == "nightly":
        base_version = read_assignment(shared_sdk_version_path, "platform_sdk_version")
        if not re.fullmatch(SEMVER_CORE_PATTERN, base_version):
            raise StampError(f"nightly base SDK version must be SemVer core MAJOR.MINOR.PATCH: {base_version}")
        if not re.fullmatch(r"\d{14}", nightly_timestamp):
            raise StampError("nightly timestamp must be YYYYMMDDHHMMSS")
        return f"{base_version}.dev{nightly_timestamp}"

    if cadence == "rc":
        match = re.fullmatch(rf"({SEMVER_CORE_PATTERN})-rc(\d+)", release_label)
        if not match:
            raise StampError(f"RC release label must look like 1.0.0-rc0: {release_label}")
        return f"{match.group(1)}rc{match.group(2)}"

    if cadence == "release":
        if not re.fullmatch(SEMVER_CORE_PATTERN, release_label):
            raise StampError(f"stable release label must be SemVer core MAJOR.MINOR.PATCH: {release_label}")
        return release_label

    raise StampError(f"unsupported cadence for SDK version stamping: {cadence}")


def stamp_sdk_version(
    source_root: Path,
    sdk_id: str,
    cadence: Cadence,
    release_label: str,
    nightly_timestamp: str,
) -> str:
    safe_sdk_id(sdk_id)
    shared_sdk_version_path = source_root / "packages/nmp_common/src/nmp/common/version.py"
    generated_sdk_version_path = source_root / "sdk/python/nemo-platform/src/nemo_platform/_version.py"
    sdk_version = resolve_sdk_version(cadence, release_label, nightly_timestamp, shared_sdk_version_path)

    replace_assignment(shared_sdk_version_path, "platform_sdk_version", sdk_version)
    replace_assignment(generated_sdk_version_path, "__version__", sdk_version)
    return sdk_version


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--sdk-id", required=True)
    parser.add_argument("--cadence", required=True, choices=["nightly", "rc", "release"])
    # --release-label is unused for cadence=nightly; cadence-specific validation
    # in resolve_sdk_version() rejects empty/missing labels for rc and release.
    parser.add_argument("--release-label", default="")
    parser.add_argument("--nightly-timestamp", default="")
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="Print only the resolved version on stdout; send the human banner to stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        sdk_version = stamp_sdk_version(
            source_root=args.source_root,
            sdk_id=args.sdk_id,
            cadence=args.cadence,
            release_label=args.release_label,
            nightly_timestamp=args.nightly_timestamp,
        )
    except StampError as error:
        print(error, file=sys.stderr)
        return 1

    if args.print_version:
        # Machine-readable mode: human banner to stderr, just the version on stdout.
        print(f"Stamped sdk:{args.sdk_id} version {sdk_version}.", file=sys.stderr)
        print(sdk_version)
    else:
        print(f"Stamped sdk:{args.sdk_id} version {sdk_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
