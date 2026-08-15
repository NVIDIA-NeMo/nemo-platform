# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_copyright_fixer() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "script" / "copyright_fixer.py"
    spec = importlib.util.spec_from_file_location("copyright_fixer", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


copyright_fixer = _load_copyright_fixer()


def test_supported_file_includes_missing_osrb_file_types(tmp_path: Path) -> None:
    files = {
        "e2e/conftest.py": 'print("ok")\n',
        "k8s/helm/helm-docs-template/nemo-helm-readme.md.gotmpl": "# title\n",
        "sdk/python/nemo-platform/Brewfile": 'brew "uv"\n',
        "sdk/python/nemo-platform/bin/publish-pypi": "#!/usr/bin/env bash\n",
        "services/core/entities/alembic/README": "Generic single-database configuration.\n",
        "services/core/entities/alembic/script.py.mako": '"""${message}"""\n',
        "services/core/entities/src/nmp/core/entities/api/v2/entities/entities.http": "// Example\n",
    }

    for relpath, content in files.items():
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        assert copyright_fixer._is_supported_file(str(path))


def test_supported_file_does_not_treat_shebang_as_universal_override(tmp_path: Path) -> None:
    patch_file = tmp_path / "tarfile.py.fix"
    patch_file.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    assert not copyright_fixer._is_supported_file(str(patch_file))


def test_add_header_uses_syntax_safe_styles_for_missing_osrb_file_types(tmp_path: Path) -> None:
    files = {
        "test_case.py": ('print("ok")\n', copyright_fixer._HASH_HEADER + "\n"),
        "nemo-helm-readme.md.gotmpl": ("# title\n", copyright_fixer._HELM_TEMPLATE_HEADER + "\n"),
        "helm-template.yaml": ("apiVersion: v1\n", copyright_fixer._HASH_HEADER + "\n"),
        "Brewfile": ('brew "uv"\n', copyright_fixer._HASH_HEADER + "\n"),
        "publish-pypi": (
            "#!/usr/bin/env bash\nset -e\n",
            "#!/usr/bin/env bash\n" + copyright_fixer._HASH_HEADER + "\n",
        ),
        "README": ("Generic single-database configuration.\n", copyright_fixer._HTML_HEADER + "\n"),
        "script.py.mako": ('"""${message}"""\n', copyright_fixer._HASH_HEADER + "\n"),
        "entities.http": ("// Example\n", copyright_fixer._SLASH_HEADER + "\n"),
    }

    for filename, (content, expected_prefix) in files.items():
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")

        assert copyright_fixer._add_header(str(path))
        assert path.read_text(encoding="utf-8").startswith(expected_prefix)


def test_helm_template_header_keeps_spdx_identifier_on_own_line() -> None:
    assert "\nSPDX-License-Identifier: Apache-2.0\n*/}}\n" in copyright_fixer._HELM_TEMPLATE_HEADER
    assert "SPDX-License-Identifier: Apache-2.0 */}}" not in copyright_fixer._HELM_TEMPLATE_HEADER


def test_inline_helm_template_header_is_not_accepted() -> None:
    inline_header = (
        "{{/* SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. "
        "All rights reserved. */}}\n"
        "{{/* SPDX-License-Identifier: Apache-2.0 */}}\n"
    )

    assert not copyright_fixer._has_correct_spdx_header(inline_header)


def test_include_can_target_files_under_copyrightignore_excluded_directories(tmp_path: Path) -> None:
    repo = copyright_fixer.Repo.init(tmp_path)
    ignored_file = tmp_path / "e2e" / "conftest.py"
    ignored_file.parent.mkdir()
    ignored_file.write_text('print("ok")\n', encoding="utf-8")
    (tmp_path / ".copyrightignore").write_text("e2e/\n", encoding="utf-8")
    repo.index.add([".copyrightignore", "e2e/conftest.py"])

    default_files = copyright_fixer._collect_files_from_dir(str(tmp_path))
    included_files = copyright_fixer._collect_files_from_dir(str(tmp_path), include=["e2e/conftest.py"])

    assert str(ignored_file) not in default_files
    assert str(ignored_file) in included_files


def test_proprietary_license_detection_ignores_fixer_source_literals() -> None:
    source = Path(copyright_fixer.__file__).read_text(encoding="utf-8")[:4096]

    assert not copyright_fixer._has_proprietary_license(source)
    assert copyright_fixer._has_proprietary_license(
        "# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n"
        "# SPDX-License-Identifier: LicenseRef-NvidiaProprietary\n"
    )
