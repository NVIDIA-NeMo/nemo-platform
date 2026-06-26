# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from docs._scripts.lint_python_snippets import (
    extract_python_snippets,
    find_doc_files,
    prepare_type_check_file,
    syntax_check,
    translate_line_number,
)


def test_find_doc_files_includes_mdx_and_skips_node_modules(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    mdx = docs_dir / "page.mdx"
    md = docs_dir / "page.md"
    ignored = docs_dir / "node_modules" / "package" / "README.md"
    ignored.parent.mkdir(parents=True)
    mdx.write_text("# Page\n", encoding="utf-8")
    md.write_text("# Page\n", encoding="utf-8")
    ignored.write_text("# Ignored\n", encoding="utf-8")

    assert find_doc_files([docs_dir]) == [md, mdx]


def test_extract_python_snippets_supports_mdx_info_strings_and_indent(tmp_path: Path) -> None:
    doc = tmp_path / "page.mdx"
    doc.write_text(
        """<Tabs>

    ```python title="example.py"
    value = 1
    ```

```py
print(value)
```
</Tabs>
""",
        encoding="utf-8",
    )

    snippets = extract_python_snippets(doc)

    assert [(snippet.start_line, snippet.source) for snippet in snippets] == [
        (4, "value = 1"),
        (8, "print(value)"),
    ]


def test_extract_python_snippets_skip_markers(tmp_path: Path) -> None:
    doc = tmp_path / "page.mdx"
    doc.write_text(
        """<!-- @nemo-docs: skip-python-snippet-check -->
```python
this is intentionally not python
```

<!-- @nemo-nb: skip-type-check -->
```python
from litellm import completion
completion(model="demo", messages=[])
```

```python
print("kept")
```
""",
        encoding="utf-8",
    )

    snippets = extract_python_snippets(doc)

    assert [(snippet.start_line, snippet.type_check, snippet.source) for snippet in snippets] == [
        (8, False, 'from litellm import completion\ncompletion(model="demo", messages=[])'),
        (13, True, 'print("kept")'),
    ]


def test_syntax_check_reports_original_doc_line(tmp_path: Path) -> None:
    doc = tmp_path / "page.mdx"
    doc.write_text(
        """# Page

```python
print("ok")
if True
    print("bad")
```
""",
        encoding="utf-8",
    )

    diagnostics = syntax_check(extract_python_snippets(doc))

    assert len(diagnostics) == 1
    assert diagnostics[0].line == 5
    assert diagnostics[0].column == 8
    assert diagnostics[0].path == doc


def test_syntax_check_allows_ipython_line_magics(tmp_path: Path) -> None:
    doc = tmp_path / "page.mdx"
    doc.write_text(
        """```python
%pip install -q datasets
!echo ready
value = 1
```
""",
        encoding="utf-8",
    )

    assert syntax_check(extract_python_snippets(doc)) == []


def test_prepare_type_check_file_preserves_line_mapping(tmp_path: Path) -> None:
    doc = tmp_path / "page.mdx"
    doc.write_text(
        """```python
value = 1
```

<!-- @nemo-docs: skip-python-type-check -->
```python
skipped = unknown
```

```python
print(value)
```
""",
        encoding="utf-8",
    )
    snippets = extract_python_snippets(doc)

    prepared = prepare_type_check_file(doc, snippets, tmp_path)

    assert prepared is not None
    assert prepared.temp_path.read_text(encoding="utf-8") == "value = 1\n\nprint(value)\n"
    assert prepared.line_mapping == (2, 2, 11, 11)
    assert translate_line_number(3, prepared.line_mapping) == 11
