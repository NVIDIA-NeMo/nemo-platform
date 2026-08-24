# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for MyST directive stripping in notebooks."""

import tempfile
from pathlib import Path

from nemo_nb.md_to_notebook import MarkdownToNotebookConverter, strip_myst_directives


def test_strip_tip_directive():
    """Test that {tip} directive fences are removed but content is kept."""
    content = """# Header

:::{tip}
This is a helpful tip for users.
:::

More content."""

    result = strip_myst_directives(content)

    # Directive fences should be removed
    assert ":::{tip}" not in result
    assert ":::" not in result

    # Content should be preserved
    assert "This is a helpful tip for users." in result
    assert "# Header" in result
    assert "More content." in result


def test_strip_note_warning_directives():
    """Test that various admonition directives are stripped."""
    content = """:::{note}
Important note
:::

:::{warning}
Be careful!
:::

:::{caution}
Watch out
:::"""

    result = strip_myst_directives(content)

    # All directive fences should be removed
    assert ":::{note}" not in result
    assert ":::{warning}" not in result
    assert ":::{caution}" not in result

    # Content should be preserved
    assert "Important note" in result
    assert "Be careful!" in result
    assert "Watch out" in result


def test_strip_empty_cross_references():
    """Test that empty MyST cross-references are removed."""
    content = """Check the [](quickstart-guide) for more info.

See [](api-reference) and [](troubleshooting).

Regular [link with text](http://example.com) should stay."""

    result = strip_myst_directives(content)

    # Empty cross-references should be removed
    assert "[](quickstart-guide)" not in result
    assert "[](api-reference)" not in result
    assert "[](troubleshooting)" not in result

    # Regular links with text should be preserved
    assert "[link with text](http://example.com)" in result


def test_strip_myst_labels():
    """Test that MyST labels are removed."""
    content = """(my-label)=

# Header

Some content

(another-label)=

## Subheader"""

    result = strip_myst_directives(content)

    # Labels should be removed
    assert "(my-label)=" not in result
    assert "(another-label)=" not in result

    # Headers and content should be preserved
    assert "# Header" in result
    assert "## Subheader" in result
    assert "Some content" in result


def test_strip_code_directives():
    """Test that code directive fences are removed."""
    content = """```{literalinclude} file.py
:lines: 1-10
```

Regular code should stay:

```python
print("hello")
```"""

    result = strip_myst_directives(content)

    # Code directive should be removed
    assert "{literalinclude}" not in result

    # Regular code fence should be preserved
    assert "```python" in result
    assert 'print("hello")' in result


def test_converter_strips_myst_when_requested():
    """Test that the converter strips MyST directives when strip_myst=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a markdown file with MyST directives
        md_file = tmpdir / "test.md"
        md_file.write_text(
            """<!-- @nemo-nb: process -->

# Tutorial

:::{tip}
This tip should be plain text in the notebook.
:::

Check [](some-reference) for more info.

(my-label)=

## Section

```python
print("hello")
```
"""
        )

        # Convert to notebook with MyST stripping enabled
        converter = MarkdownToNotebookConverter()
        notebook = converter.convert(md_file, strip_myst=True)

        # Check that MyST directives are not in the notebook
        all_source = ""
        for cell in notebook["cells"]:
            all_source += "".join(cell.get("source", []))

        # MyST syntax should be removed
        assert ":::{tip}" not in all_source
        assert ":::" not in all_source  # Closing fence
        assert "[](some-reference)" not in all_source
        assert "(my-label)=" not in all_source

        # Content should be preserved
        assert "This tip should be plain text in the notebook." in all_source
        assert "# Tutorial" in all_source
        assert "## Section" in all_source
        assert 'print("hello")' in all_source


def test_converter_preserves_myst_by_default():
    """Test that the converter preserves MyST directives by default (for Sphinx)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a markdown file with MyST directives
        md_file = tmpdir / "test.md"
        md_file.write_text(
            """<!-- @nemo-nb: process -->

:::{tip}
Important tip
:::
"""
        )

        # Convert to notebook WITHOUT stripping (default)
        converter = MarkdownToNotebookConverter()
        notebook = converter.convert(md_file)

        # Check that MyST directives ARE preserved
        all_source = ""
        for cell in notebook["cells"]:
            all_source += "".join(cell.get("source", []))

        # MyST syntax should be preserved for Sphinx processing
        assert ":::{tip}" in all_source
        assert "Important tip" in all_source


def test_nested_admonitions():
    """Test that nested admonition directives are handled."""
    content = """::::{note}
Outer note

:::{tip}
Inner tip
:::

More outer content
::::"""

    result = strip_myst_directives(content)

    # All directive fences should be removed
    assert "::::" not in result
    assert ":::" not in result

    # Content should be preserved
    assert "Outer note" in result
    assert "Inner tip" in result
    assert "More outer content" in result


def test_mixed_content():
    """Test realistic content with mixed MyST directives."""
    content = """<!-- @nemo-nb: process -->
(tutorial-deploy)=

# Deploy Models

Deploy models from NGC. See [](quickstart) for setup.

:::{tip}
Use the CLI for faster deployment.
:::

```{literalinclude} example.yaml
:language: yaml
```

```python
# Regular code
sdk.models.create_deployment()
```

:::{warning}
Make sure GPU resources are configured.
:::"""

    result = strip_myst_directives(content)

    # MyST directives should be removed
    assert "(tutorial-deploy)=" not in result
    assert "[](quickstart)" not in result
    assert ":::{tip}" not in result
    assert ":::{warning}" not in result
    assert "{literalinclude}" not in result

    # Content should be preserved
    assert "# Deploy Models" in result
    assert "Use the CLI for faster deployment." in result
    assert "Make sure GPU resources are configured." in result
    assert "```python" in result
    assert "sdk.models.create_deployment()" in result
