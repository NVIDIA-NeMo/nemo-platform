# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def load_bundle_metadata_module() -> ModuleType:
    script_path = Path(__file__).parents[3] / ".github/scripts/write_release_bundle_metadata.py"
    spec = importlib.util.spec_from_file_location("write_release_bundle_metadata", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle_metadata = load_bundle_metadata_module()
BundleMetadataError = bundle_metadata.BundleMetadataError


def selected_artifacts(*artifacts: dict[str, str]) -> str:
    return json.dumps(list(artifacts), separators=(",", ":"))


def write_wheel(
    sdk_artifacts_dir: Path,
    sdk_id: str,
    *,
    filename: str = "nemo_platform-1.0.0-py3-none-any.whl",
    version: str = "1.0.0",
    metadata_files: list[str] | None = None,
) -> Path:
    artifact_dir = sdk_artifacts_dir / f"release-sdk-{sdk_id}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = artifact_dir / filename
    metadata_files = metadata_files if metadata_files is not None else ["nemo_platform-1.0.0.dist-info/METADATA"]

    with zipfile.ZipFile(wheel_path, "w") as wheel:
        for metadata_file in metadata_files:
            wheel.writestr(
                metadata_file,
                f"""Metadata-Version: 2.1
Name: nemo-platform
Version: {version}
""",
            )
        wheel.writestr("nemo_platform-1.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")

    return wheel_path


def write_metadata(
    tmp_path: Path,
    *,
    selected: str | None = None,
    cadence: str = "release",
    release_label: str = "1.0.0",
    release_date_json: str = '"2026-06-30"',
    source_sha: str = "a" * 40,
) -> tuple[Path, Path]:
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    bundle_dir = tmp_path / "release-bundle"
    write_wheel(sdk_artifacts_dir, "nemo-platform")

    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=sdk_artifacts_dir,
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected or selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
        cadence=cadence,
        release_label=release_label,
        release_date_json=release_date_json,
        source_sha=source_sha,
    )
    return sdk_artifacts_dir, bundle_dir


def read_manifest(bundle_dir: Path) -> dict[str, object]:
    return json.loads((bundle_dir / "release-manifest.json").read_text(encoding="utf-8"))


def parse_checksums(bundle_dir: Path) -> dict[str, str]:
    entries = {}
    for line in (bundle_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, path = line.split("  ", 1)
        entries[path] = digest
    return entries


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_one_sdk_wheel_writes_manifest_and_checksums(tmp_path: Path):
    sdk_artifacts_dir, bundle_dir = write_metadata(tmp_path)
    source_wheel = sdk_artifacts_dir / "release-sdk-nemo-platform/nemo_platform-1.0.0-py3-none-any.whl"
    bundled_wheel = bundle_dir / "wheels/nemo_platform-1.0.0-py3-none-any.whl"

    assert bundled_wheel.read_bytes() == source_wheel.read_bytes()
    assert read_manifest(bundle_dir) == {
        "cadence": "release",
        "release_label": "1.0.0",
        "release_date": "2026-06-30",
        "source_sha": "a" * 40,
        "artifacts": [
            {
                "type": "sdk",
                "id": "nemo-platform",
                "version": "1.0.0",
                "path": "wheels/nemo_platform-1.0.0-py3-none-any.whl",
            }
        ],
    }

    assert parse_checksums(bundle_dir) == {
        "release-manifest.json": sha256(bundle_dir / "release-manifest.json"),
        "wheels/nemo_platform-1.0.0-py3-none-any.whl": sha256(bundled_wheel),
    }


def test_one_sdk_wheel_can_be_downloaded_directly_to_artifacts_dir(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    bundle_dir = tmp_path / "release-bundle"
    nested_wheel = write_wheel(sdk_artifacts_dir, "nemo-platform")
    direct_wheel = sdk_artifacts_dir / nested_wheel.name
    nested_wheel.rename(direct_wheel)
    nested_wheel.parent.rmdir()

    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=sdk_artifacts_dir,
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
        cadence="release",
        release_label="1.0.0",
        release_date_json="null",
        source_sha="a" * 40,
    )

    bundled_wheel = bundle_dir / "wheels/nemo_platform-1.0.0-py3-none-any.whl"
    assert bundled_wheel.read_bytes() == direct_wheel.read_bytes()
    assert read_manifest(bundle_dir)["artifacts"][0]["path"] == (  # type: ignore[index]
        "wheels/nemo_platform-1.0.0-py3-none-any.whl"
    )


def test_release_date_json_null_becomes_manifest_null(tmp_path: Path):
    _, bundle_dir = write_metadata(tmp_path, release_date_json="null")

    assert read_manifest(bundle_dir)["release_date"] is None


def test_checksums_only_include_manifest_and_wheels(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    bundle_dir = tmp_path / "release-bundle"
    write_wheel(sdk_artifacts_dir, "nemo-platform")
    bundle_dir.mkdir()
    (bundle_dir / "stale.txt").write_text("old file\n", encoding="utf-8")

    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=sdk_artifacts_dir,
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
        cadence="release",
        release_label="1.0.0",
        release_date_json="null",
        source_sha="a" * 40,
    )

    assert set(parse_checksums(bundle_dir)) == {
        "release-manifest.json",
        "wheels/nemo_platform-1.0.0-py3-none-any.whl",
    }


def test_rc_label_stays_release_label_and_wheel_version_comes_from_metadata(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    bundle_dir = tmp_path / "release-bundle"
    write_wheel(
        sdk_artifacts_dir,
        "nemo-platform",
        filename="nemo_platform-1.0.0rc0-py3-none-any.whl",
        version="1.0.0rc0",
    )

    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=sdk_artifacts_dir,
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
        cadence="rc",
        release_label="1.0.0-rc0",
        release_date_json="null",
        source_sha="b" * 40,
    )

    manifest = read_manifest(bundle_dir)
    assert manifest["release_label"] == "1.0.0-rc0"
    assert manifest["artifacts"][0]["version"] == "1.0.0rc0"  # type: ignore[index]


def test_missing_sdk_artifact_directory_fails_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="missing downloaded SDK artifact directory"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_zero_wheels_fails_clearly(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    (sdk_artifacts_dir / "release-sdk-nemo-platform").mkdir(parents=True)

    with pytest.raises(BundleMetadataError, match="expected exactly one wheel"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=sdk_artifacts_dir,
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_multiple_wheels_for_one_sdk_fails_clearly(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    write_wheel(sdk_artifacts_dir, "nemo-platform")
    write_wheel(
        sdk_artifacts_dir,
        "nemo-platform",
        filename="nemo_platform-1.0.1-py3-none-any.whl",
        version="1.0.1",
    )

    with pytest.raises(BundleMetadataError, match="expected exactly one wheel"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=sdk_artifacts_dir,
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_multiple_directly_downloaded_wheels_fail_clearly(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    nested_wheel = write_wheel(sdk_artifacts_dir, "nemo-platform")
    direct_wheel = sdk_artifacts_dir / nested_wheel.name
    nested_wheel.rename(direct_wheel)
    nested_wheel.parent.rmdir()
    write_wheel(
        sdk_artifacts_dir,
        "extra",
        filename="nemo_platform-1.0.1-py3-none-any.whl",
        version="1.0.1",
    ).rename(
        sdk_artifacts_dir / "nemo_platform-1.0.1-py3-none-any.whl",
    )

    with pytest.raises(BundleMetadataError, match="expected exactly one wheel"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=sdk_artifacts_dir,
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_unsupported_artifact_type_fails_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="unsupported artifact type"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "helm", "id": "platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_container_artifacts_become_metadata_only_entries(tmp_path: Path):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    bundle_dir = tmp_path / "release-bundle"
    write_wheel(sdk_artifacts_dir, "nemo-platform")

    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=sdk_artifacts_dir,
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected_artifacts(
            {"type": "sdk", "id": "nemo-platform"},
            {"type": "container", "id": "nmp-automodel-tasks"},
            {"type": "container", "id": "nmp-unsloth-training"},
        ),
        cadence="rc",
        release_label="1.0.0-rc1",
        release_date_json="null",
        source_sha="c" * 40,
    )

    artifacts = read_manifest(bundle_dir)["artifacts"]
    assert artifacts[1:] == [  # type: ignore[index]
        {"type": "container", "id": "nmp-automodel-tasks", "version": "1.0.0-rc1"},
        {"type": "container", "id": "nmp-unsloth-training", "version": "1.0.0-rc1"},
    ]
    # Container entries are metadata-only: no path, and nothing extra in checksums.
    assert set(parse_checksums(bundle_dir)) == {
        "release-manifest.json",
        "wheels/nemo_platform-1.0.0-py3-none-any.whl",
    }


def test_container_only_selection_is_valid(tmp_path: Path):
    bundle_dir = tmp_path / "release-bundle"
    bundle_metadata.write_release_bundle_metadata(
        sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
        bundle_dir=bundle_dir,
        selected_artifacts_json=selected_artifacts(
            {"type": "container", "id": "nmp-automodel-tasks"},
            {"type": "container", "id": "nmp-unsloth-training"},
        ),
        cadence="release",
        release_label="1.0.0",
        release_date_json="null",
        source_sha="a" * 40,
    )

    # Container-only bundle: only container entries, no wheels, checksums = manifest only.
    assert read_manifest(bundle_dir)["artifacts"] == [
        {"type": "container", "id": "nmp-automodel-tasks", "version": "1.0.0"},
        {"type": "container", "id": "nmp-unsloth-training", "version": "1.0.0"},
    ]
    assert set(parse_checksums(bundle_dir)) == {"release-manifest.json"}


def test_empty_selection_fails_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="non-empty list"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json="[]",
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_duplicate_container_ids_fail_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="duplicate container id: nmp-automodel-tasks"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts(
                {"type": "sdk", "id": "nemo-platform"},
                {"type": "container", "id": "nmp-automodel-tasks"},
                {"type": "container", "id": "nmp-automodel-tasks"},
            ),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_unsafe_container_id_fails_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="container id must be a safe single path segment"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts(
                {"type": "sdk", "id": "nemo-platform"},
                {"type": "container", "id": "../evil"},
            ),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_duplicate_selected_sdk_ids_fail_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="duplicate sdk id: nemo-platform"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=tmp_path / "downloaded-artifacts",
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts(
                {"type": "sdk", "id": "nemo-platform"},
                {"type": "sdk", "id": "nemo-platform"},
            ),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )


def test_malformed_release_date_json_fails_clearly(tmp_path: Path):
    with pytest.raises(BundleMetadataError, match="release_date_json must be valid JSON"):
        write_metadata(tmp_path, release_date_json="2026-06-30")


@pytest.mark.parametrize(
    "metadata_files",
    [
        [],
        [
            "nemo_platform-1.0.0.dist-info/METADATA",
            "other-1.0.0.dist-info/METADATA",
        ],
    ],
)
def test_missing_or_duplicate_wheel_metadata_fails_clearly(tmp_path: Path, metadata_files: list[str]):
    sdk_artifacts_dir = tmp_path / "downloaded-artifacts"
    write_wheel(sdk_artifacts_dir, "nemo-platform", metadata_files=metadata_files)

    with pytest.raises(BundleMetadataError, match="expected exactly one METADATA file"):
        bundle_metadata.write_release_bundle_metadata(
            sdk_artifacts_dir=sdk_artifacts_dir,
            bundle_dir=tmp_path / "release-bundle",
            selected_artifacts_json=selected_artifacts({"type": "sdk", "id": "nemo-platform"}),
            cadence="release",
            release_label="1.0.0",
            release_date_json="null",
            source_sha="a" * 40,
        )
