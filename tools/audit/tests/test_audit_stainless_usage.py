# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "audit_stainless_usage.py"


def run_audit(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT_PATH.as_posix(), root.as_posix(), *args],
        capture_output=True,
        check=False,
        text=True,
    )


def test_audit_flags_active_legacy_sdk_import(tmp_path: Path) -> None:
    source_path = tmp_path / "packages/example/src/example/client.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from nemo_platform import NeMoPlatform\n\n"
        "def build_client() -> NeMoPlatform:\n"
        '    return NeMoPlatform(base_url="http://localhost:8080")\n',
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["active_dependency_files"] == 1
    assert payload["summary"]["active_dependency_owners"] == 1
    assert payload["summary"]["legacy_sdk_import_files"] == 1
    assert payload["summary"]["legacy_sdk_import_owners"] == 1
    assert payload["affected_paths"] == ["packages/example/src/example/client.py"]
    assert payload["active_dependency_owner_summary"]["package:example"]["files"] == 1
    assert payload["legacy_sdk_import_owner_summary"]["package:example"]["files"] == 1

    strict_result = run_audit(tmp_path, "--strict")

    assert strict_result.returncode == 1


def test_strict_audit_rejects_invalid_python_with_legacy_sdk_import(tmp_path: Path) -> None:
    source_path = tmp_path / "services/core/models/src/nmp/core/models/broken.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from nemo_platform import NeMoPlatform\n\ndef broken(:\n    pass\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json", "--strict")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["summary"]["legacy_sdk_import_files"] == 1
    assert payload["legacy_sdk_import_paths"] == [
        "services/core/models/src/nmp/core/models/broken.py",
    ]
    assert payload["legacy_sdk_import_owner_summary"]["service:core/models"]["files"] == 1


def test_audit_treats_stainless_yaml_as_metadata(tmp_path: Path) -> None:
    metadata_path = tmp_path / "sdk/stainless.yaml"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        "# Stainless metadata used by CLI generation\n"
        "resources:\n"
        "  jobs:\n"
        "    x-stainless-pagination-property: items\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json", "--strict")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["active_dependency_files"] == 0
    assert payload["summary"]["active_dependency_owners"] == 0
    assert payload["summary"]["legacy_sdk_import_files"] == 0
    assert payload["summary"]["legacy_sdk_import_owners"] == 0
    assert payload["summary"]["findings_by_category"] == {"sdk-metadata": 2}


def test_audit_ignores_plugin_package_imports_without_legacy_sdk(tmp_path: Path) -> None:
    source_path = tmp_path / "packages/example/src/example/client.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from nemo_platform_plugin.jobs.client import JobsClient\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json", "--strict")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["files_with_findings"] == 0


def test_audit_groups_active_findings_by_service_and_plugin(tmp_path: Path) -> None:
    service_path = tmp_path / "services/core/files/src/nmp/core/files/compile.py"
    service_path.parent.mkdir(parents=True)
    service_path.write_text(
        "from nemo_platform import AsyncNeMoPlatform\n",
        encoding="utf-8",
    )

    plugin_path = tmp_path / "plugins/nemo-example/src/nemo_example_plugin/run.py"
    plugin_path.parent.mkdir(parents=True)
    plugin_path.write_text(
        "from nemo_platform import NeMoPlatform\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["active_dependency_owners"] == 2
    assert payload["active_dependency_owner_summary"]["service:core/files"]["files"] == 1
    assert payload["active_dependency_owner_summary"]["plugin:nemo-example"]["files"] == 1


def test_audit_does_not_count_package_docs_as_active_dependencies(tmp_path: Path) -> None:
    docs_path = tmp_path / "packages/example/docs/usage.md"
    docs_path.parent.mkdir(parents=True)
    docs_path.write_text(
        "This mentions NeMoPlatform and Stainless for migration guidance.\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--json", "--strict")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["active_dependency_files"] == 0
    assert payload["summary"]["findings_by_category"] == {"docs": 2}


def test_default_output_focuses_on_legacy_sdk_import_owners(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs/migration.md"
    docs_path.parent.mkdir(parents=True)
    docs_path.write_text(
        "Stainless docs mention NeMoPlatform.\n",
        encoding="utf-8",
    )

    metadata_path = tmp_path / "sdk/stainless.yaml"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        "x-stainless-pagination-property: items\n",
        encoding="utf-8",
    )

    source_path = tmp_path / "plugins/nemo-example/src/nemo_example_plugin/run.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from nemo_platform import AsyncNeMoPlatform\n"
        "from nemo_platform_plugin.client.adapter import client_from_platform\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--limit", "10")

    assert result.returncode == 0
    assert "Legacy Python SDK import audit" in result.stdout
    assert "Files importing legacy SDK: 1" in result.stdout
    assert "Legacy SDK imports by owner" in result.stdout
    assert "plugin:nemo-example" in result.stdout
    assert "\nLegacy SDK import lines\n" not in result.stdout
    assert "from nemo_platform import AsyncNeMoPlatform" not in result.stdout
    assert "Stainless-specific tooling and metadata" not in result.stdout
    assert "Documentation findings" not in result.stdout
    assert "legacy-sdk-adapter" not in result.stdout

    adjacent_result = run_audit(tmp_path, "--limit", "10", "--show-adjacent")

    assert adjacent_result.returncode == 0
    assert "Adjacent dependency summary" in adjacent_result.stdout
    assert "legacy-sdk-adapter" in adjacent_result.stdout
    assert "\nAdjacent dependency files\n" not in adjacent_result.stdout

    adjacent_lines_result = run_audit(tmp_path, "--limit", "10", "--show-adjacent", "--show-lines")

    assert adjacent_lines_result.returncode == 0
    assert "\nAdjacent dependency files\n" in adjacent_lines_result.stdout
    assert "L2 legacy-sdk-adapter: from nemo_platform_plugin.client.adapter import client_from_platform" in (
        adjacent_lines_result.stdout
    )


def test_show_lines_prints_legacy_sdk_import_line_details(tmp_path: Path) -> None:
    source_path = tmp_path / "services/core/models/src/nmp/core/models/client.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from nemo_platform import NeMoPlatform\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path, "--show-lines")

    assert result.returncode == 0
    assert "Legacy SDK imports by owner" in result.stdout
    assert "\nLegacy SDK import lines\n" in result.stdout
    assert "services/core/models/src/nmp/core/models/client.py (1 findings)" in result.stdout
    assert "L1 legacy-sdk-import: from nemo_platform import NeMoPlatform" in result.stdout


def test_default_output_shows_all_import_files(tmp_path: Path) -> None:
    first_path = tmp_path / "services/core/models/src/nmp/core/models/first.py"
    first_path.parent.mkdir(parents=True)
    first_path.write_text(
        "from nemo_platform import NeMoPlatform\n",
        encoding="utf-8",
    )

    second_path = tmp_path / "services/core/models/src/nmp/core/models/second.py"
    second_path.write_text(
        "from nemo_platform import AsyncNeMoPlatform\n",
        encoding="utf-8",
    )

    result = run_audit(tmp_path)

    assert result.returncode == 0
    assert "services/core/models/src/nmp/core/models/first.py" in result.stdout
    assert "services/core/models/src/nmp/core/models/second.py" in result.stdout
    assert "more files hidden" not in result.stdout
    assert "more owners hidden" not in result.stdout
