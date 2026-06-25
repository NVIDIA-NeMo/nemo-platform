# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Write release bundle metadata for downloaded SDK wheel artifacts.

Container artifacts are metadata-only manifest entries: the image bits are
built and staged by the release consumer from its dev registry at the bundle's
source SHA, so container entries carry no path or checksum.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Literal

Cadence = Literal["nightly", "rc", "release"]


class BundleMetadataError(Exception):
    """Raised when the release bundle metadata cannot be written safely."""


def safe_artifact_id(artifact_type: str, artifact_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", artifact_id) or artifact_id in {".", ".."}:
        raise BundleMetadataError(f"selected {artifact_type} id must be a safe single path segment: {artifact_id}")
    return artifact_id


def parse_release_date_json(value: str) -> str | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise BundleMetadataError(f"release_date_json must be valid JSON: {error.msg}") from error

    if parsed is not None and not isinstance(parsed, str):
        raise BundleMetadataError("release_date_json must be a JSON string or null")
    return parsed


def artifact_ref(artifact_type: object, artifact_id: object) -> str:
    return f"{artifact_type}:{artifact_id}"


def parse_selected_artifact_ids(value: str) -> dict[str, list[str]]:
    """Parse selected_artifacts_json into ids grouped by artifact type."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise BundleMetadataError(f"selected_artifacts_json must be valid JSON: {error.msg}") from error

    if not isinstance(parsed, list) or not parsed:
        raise BundleMetadataError("selected_artifacts_json must be a non-empty list")

    ids_by_type: dict[str, list[str]] = {"sdk": [], "container": []}
    seen: dict[str, set[str]] = {artifact_type: set() for artifact_type in ids_by_type}
    for artifact in parsed:
        if not isinstance(artifact, dict):
            raise BundleMetadataError("selected_artifacts_json entries must be objects")

        artifact_type = artifact.get("type")
        artifact_id = artifact.get("id")
        if artifact_type not in ids_by_type:
            raise BundleMetadataError(
                f"unsupported artifact type in bundle selection: {artifact_ref(artifact_type, artifact_id)}"
            )
        if not isinstance(artifact_id, str) or not artifact_id:
            raise BundleMetadataError(f"selected {artifact_type} artifact id must be a non-empty string")

        checked_id = safe_artifact_id(artifact_type, artifact_id)
        if checked_id in seen[artifact_type]:
            raise BundleMetadataError(f"selected_artifacts_json contains duplicate {artifact_type} id: {checked_id}")

        seen[artifact_type].add(checked_id)
        ids_by_type[artifact_type].append(checked_id)

    # A bundle may be SDK-only, container-only, or mixed; the non-empty-list
    # check above already guarantees at least one artifact of some type.
    return ids_by_type


def find_sdk_wheel(sdk_artifacts_dir: Path, sdk_id: str, *, single_sdk_artifact: bool) -> Path:
    artifact_dir = sdk_artifacts_dir / f"release-sdk-{sdk_id}"
    if not artifact_dir.is_dir():
        if single_sdk_artifact:
            # download-artifact extracts one pattern match directly into the target path.
            wheels = sorted(sdk_artifacts_dir.glob("*.whl"))
            if wheels:
                if len(wheels) != 1:
                    raise BundleMetadataError(f"expected exactly one wheel in {sdk_artifacts_dir}, found {len(wheels)}")
                return wheels[0]
        raise BundleMetadataError(f"missing downloaded SDK artifact directory: {artifact_dir}")

    wheels = sorted(artifact_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise BundleMetadataError(f"expected exactly one wheel in {artifact_dir}, found {len(wheels)}")
    return wheels[0]


def read_wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as wheel:
        metadata_files = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise BundleMetadataError(
                f"expected exactly one METADATA file in wheel {path.name}, found {len(metadata_files)}"
            )

        metadata = BytesParser(policy=default).parsebytes(wheel.read(metadata_files[0]))

    version = metadata["Version"]
    if not version:
        raise BundleMetadataError(f"wheel metadata must include Version: {path.name}")
    return str(version)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_relative_path(bundle_dir: Path, path: Path) -> str:
    return path.relative_to(bundle_dir).as_posix()


def write_checksums(bundle_dir: Path) -> Path:
    checksums_path = bundle_dir / "checksums.txt"
    files = [
        bundle_dir / "release-manifest.json",
        *sorted(path for path in (bundle_dir / "wheels").rglob("*") if path.is_file()),
    ]

    with checksums_path.open("w", encoding="utf-8") as checksums:
        for path in files:
            checksums.write(f"{file_sha256(path)}  {bundle_relative_path(bundle_dir, path)}\n")

    return checksums_path


def prepare_bundle_dir(bundle_dir: Path) -> Path:
    wheels_dir = bundle_dir / "wheels"
    if wheels_dir.exists():
        shutil.rmtree(wheels_dir)

    bundle_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("release-manifest.json", "checksums.txt"):
        path = bundle_dir / filename
        if path.exists():
            path.unlink()

    wheels_dir.mkdir()
    return wheels_dir


def write_release_bundle_metadata(
    *,
    sdk_artifacts_dir: Path,
    bundle_dir: Path,
    selected_artifacts_json: str,
    cadence: Cadence,
    release_label: str,
    release_date_json: str,
    source_sha: str,
) -> dict[str, object]:
    if not release_label:
        raise BundleMetadataError("release_label is required")
    if not source_sha:
        raise BundleMetadataError("source_sha is required")

    ids_by_type = parse_selected_artifact_ids(selected_artifacts_json)
    sdk_ids = ids_by_type["sdk"]
    release_date = parse_release_date_json(release_date_json)
    wheels_dir = prepare_bundle_dir(bundle_dir)

    artifacts: list[dict[str, str]] = []
    for sdk_id in sdk_ids:
        source_wheel = find_sdk_wheel(sdk_artifacts_dir, sdk_id, single_sdk_artifact=len(sdk_ids) == 1)
        wheel_version = read_wheel_version(source_wheel)
        wheel_path = wheels_dir / source_wheel.name
        if wheel_path.exists():
            raise BundleMetadataError(f"duplicate wheel filename in bundle: {source_wheel.name}")

        shutil.copy2(source_wheel, wheel_path)
        artifacts.append(
            {
                "type": "sdk",
                "id": sdk_id,
                "version": wheel_version,
                "path": bundle_relative_path(bundle_dir, wheel_path),
            }
        )

    # Container artifacts are metadata-only: the consumer stages the images
    # from its dev registry by source_sha and tags them with release_label.
    for container_id in ids_by_type["container"]:
        artifacts.append(
            {
                "type": "container",
                "id": container_id,
                "version": release_label,
            }
        )

    manifest: dict[str, object] = {
        "cadence": cadence,
        "release_label": release_label,
        "release_date": release_date,
        "source_sha": source_sha,
        "artifacts": artifacts,
    }

    manifest_path = bundle_dir / "release-manifest.json"
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    write_checksums(bundle_dir)
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-artifacts-dir", required=True, type=Path)
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--selected-artifacts-json", required=True)
    parser.add_argument("--cadence", required=True, choices=["nightly", "rc", "release"])
    parser.add_argument("--release-label", required=True)
    parser.add_argument("--release-date-json", required=True)
    parser.add_argument("--source-sha", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest = write_release_bundle_metadata(
            sdk_artifacts_dir=args.sdk_artifacts_dir,
            bundle_dir=args.bundle_dir,
            selected_artifacts_json=args.selected_artifacts_json,
            cadence=args.cadence,
            release_label=args.release_label,
            release_date_json=args.release_date_json,
            source_sha=args.source_sha,
        )
    except (BundleMetadataError, OSError, zipfile.BadZipFile) as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1

    print(f"Wrote release bundle metadata for {len(manifest['artifacts'])} artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
