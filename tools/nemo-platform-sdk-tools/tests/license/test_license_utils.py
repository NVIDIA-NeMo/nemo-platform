# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for license utility functions."""

import json
from typing import Any, cast

import pytest
from nemo_platform_sdk_tools.license.license_utils import (
    get_override_key_for_package,
    normalize_package_name,
    normalize_version_for_override,
    resolve_license,
)


class TestNormalizePackageName:
    """Tests for normalize_package_name function."""

    def test_lowercase_conversion(self):
        """Test that package names are converted to lowercase."""
        assert normalize_package_name("MyPackage") == "mypackage"
        assert normalize_package_name("UPPERCASE") == "uppercase"

    def test_underscore_to_dash(self):
        """Test that underscores are converted to dashes."""
        assert normalize_package_name("my_package") == "my-package"
        assert normalize_package_name("test_pkg_name") == "test-pkg-name"

    def test_combined_normalization(self):
        """Test combined lowercase and underscore conversion."""
        assert normalize_package_name("My_Package") == "my-package"
        assert normalize_package_name("TEST_PKG") == "test-pkg"


class TestResolveLicense:
    """Tests for resolve_license function."""

    def test_string_license(self):
        """Test resolving a simple string license."""
        assert resolve_license("MIT") == "MIT"
        assert resolve_license("Apache-2.0") == "Apache-2.0"

    def test_empty_input(self):
        """Test handling of empty input."""
        assert resolve_license("") == ""
        assert resolve_license([]) == ""

    def test_string_with_or_separator(self):
        """Test string with OR separator returns first license."""
        assert resolve_license("Apache-2.0 OR MIT") == "Apache-2.0"
        assert resolve_license("MIT OR BSD-3-Clause") == "MIT"

    def test_string_with_and_separator(self):
        """Test string with AND separator returns first license."""
        assert resolve_license("GPL-2.0 AND MIT") == "GPL-2.0"

    def test_list_without_allowed_licenses(self):
        """Test list returns first license when no allowed licenses provided."""
        assert resolve_license(["Apache-2.0", "MIT"]) == "Apache-2.0"
        assert resolve_license(["non-standard", "MIT"]) == "non-standard"

    def test_list_with_allowed_licenses_prefers_valid(self):
        """Test that allowed licenses are preferred over non-standard ones."""
        allowed = {"MIT", "APACHE-2.0", "BSD-3-CLAUSE"}

        # Should prefer MIT over non-standard
        assert resolve_license(["non-standard", "MIT"], allowed) == "MIT"

        # Should prefer Apache-2.0 (case insensitive)
        assert resolve_license(["non-standard", "Apache-2.0"], allowed) == "Apache-2.0"

        # Should prefer BSD-3-Clause
        assert resolve_license(["unknown", "BSD-3-Clause", "MIT"], allowed) == "BSD-3-Clause"

    def test_list_with_allowed_licenses_case_insensitive(self):
        """Test that license matching is case-insensitive."""
        allowed = {"MIT", "APACHE-2.0"}

        assert resolve_license(["non-standard", "mit"], allowed) == "mit"
        assert resolve_license(["unknown", "Apache-2.0"], allowed) == "Apache-2.0"
        assert resolve_license(["bad", "apache-2.0"], allowed) == "apache-2.0"

    def test_list_no_valid_licenses_returns_first(self):
        """Test that first license is returned when none are in allowed list."""
        allowed = {"MIT", "APACHE-2.0"}

        assert resolve_license(["GPL-3.0", "LGPL-2.1"], allowed) == "GPL-3.0"
        assert resolve_license(["non-standard", "unknown"], allowed) == "non-standard"

    def test_list_with_separator_in_license(self):
        """Test list with licenses containing separators."""
        allowed = {"MIT", "APACHE-2.0"}

        # Should prefer MIT OR BSD-3-Clause because MIT is in allowed (takes first part)
        result = resolve_license(["non-standard", "MIT OR BSD-3-Clause"], allowed)
        assert result == "MIT"

        # Should prefer Apache because it's in allowed (takes first part)
        result = resolve_license(["unknown", "Apache-2.0 OR MIT"], allowed)
        assert result == "Apache-2.0"

    def test_real_world_ormsgpack_case(self):
        """Test the real-world ormsgpack case that motivated this change."""
        allowed = {
            "MIT",
            "BSD-3-CLAUSE",
            "BSD-2-CLAUSE",
            "APACHE-2.0",
            "ISC",
            "ZLIB",
            "NVIDIA PROPRIETARY SOFTWARE",
        }

        # ormsgpack has ["non-standard", "MIT"] from osv-scanner
        # Should prefer MIT since it's in allowed licenses
        result = resolve_license(["non-standard", "MIT"], allowed)
        assert result == "MIT"

    def test_invalid_type_raises_error(self):
        """Test that invalid input types raise appropriate errors."""
        with pytest.raises(TypeError, match="licenses must be a list or str"):
            resolve_license(cast(Any, 123))

        with pytest.raises(TypeError, match="licenses must be a list or str"):
            resolve_license(cast(Any, None))

    def test_single_license_list(self):
        """Test list with single license."""
        assert resolve_license(["MIT"]) == "MIT"
        assert resolve_license(["Apache-2.0"], {"APACHE-2.0"}) == "Apache-2.0"


class TestNormalizeVersionForOverride:
    """Tests for normalize_version_for_override (PEP 440 local version strip)."""

    def test_strips_plus_suffix(self):
        """Version with +cu129 is normalized to base version."""
        assert normalize_version_for_override("0.14.1+cu129") == "0.14.1"
        assert normalize_version_for_override("2.9.0+cu129") == "2.9.0"

    def test_unchanged_without_plus(self):
        """Version without + is unchanged."""
        assert normalize_version_for_override("0.14.1") == "0.14.1"
        assert normalize_version_for_override("13.590.44") == "13.590.44"

    def test_strips_only_first_plus(self):
        """Only the first + and suffix are stripped."""
        assert normalize_version_for_override("0.14.1+cu129+local") == "0.14.1"


class TestGetOverrideKeyForPackage:
    """Tests for get_override_key_for_package (override lookup key)."""

    def test_base_name_unchanged(self):
        """Base name is used as key when no variant suffix."""
        assert get_override_key_for_package("torchao", "0.14.1") == "torchao"
        assert get_override_key_for_package("nvidia-ml-py", "13.590.44") == "nvidia-ml-py"

    def test_cu129_version_still_uses_name(self):
        """Package with +cu129 version still matches override by name."""
        assert get_override_key_for_package("torchao", "0.14.1+cu129") == "torchao"

    def test_name_with_cu129_suffix_stripped(self):
        """Name with -cu129 or _cu129 suffix is normalized for lookup."""
        assert get_override_key_for_package("torchao-cu129", "0.14.1") == "torchao"
        assert get_override_key_for_package("torchao_cu129", "0.14.1+cu129") == "torchao"

    def test_empty_name(self):
        """Empty name returns empty key."""
        assert get_override_key_for_package("", "0.14.1") == ""


class TestOverrideAppliedForCu129Version:
    """Verify override is applied for +cu129-style version (torchao case)."""

    def test_format_licenses_table_applies_override_for_cu129_version(self):
        """Package with version 0.14.1+cu129 and empty licenses gets override license."""
        from nemo_platform_sdk_tools.license.format_osv_licenses import format_licenses_table

        # OSV-style package with +cu129 version and no license from scanner
        json_data = {
            "results": [
                {
                    "packages": [
                        {
                            "package": {"name": "torchao", "version": "0.14.1+cu129"},
                            "licenses": [],
                        }
                    ]
                }
            ]
        }
        overrides = {"torchao": "BSD-3-Clause"}
        result = format_licenses_table(json_data, overrides=overrides, local_packages=set())
        assert "BSD-3-CLAUSE" in result
        assert "torchao" in result
        # Override was applied, so we should not see UNKNOWN for this package
        assert "✘" not in result or "BSD-3-CLAUSE" in result


class TestFormatLicenses:
    """Tests for license report formatting."""

    def test_format_licenses_fills_missing_osv_package_from_overrides(self, tmp_path):
        """A reviewed override fills an exported requirement omitted by OSV."""
        from nemo_platform_sdk_tools.license.generator import format_licenses

        license_dir = tmp_path / "third_party"
        license_dir.mkdir()
        osv_json = license_dir / "osv-licenses.json"
        osv_json.write_text(json.dumps({"results": [{"packages": []}]}), encoding="utf-8")
        (license_dir / "requirements-main.txt").write_text(
            "cloudpickle==3.1.2 ; python_version >= '3.11' \\\n"
            "    --hash=sha256:7fda9eb655c9c230dab534f1983763de5835249750e85fbcef43aaa30a9a2414\n",
            encoding="utf-8",
        )
        overrides_file = tmp_path / "overrides.yaml"
        overrides_file.write_text("overrides:\n  cloudpickle: BSD-3-Clause\n", encoding="utf-8")
        output_file = license_dir / "licenses.jsonl"

        format_licenses(osv_json, output_file, overrides_file, format_type="jsonl")

        assert output_file.read_text(encoding="utf-8") == (
            '{"name": "cloudpickle", "license": "BSD-3-CLAUSE", "compatible": true}'
        )
