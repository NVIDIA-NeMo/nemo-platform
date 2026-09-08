# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for notebook splitting by language (Python/CLI variants)."""

from nemo_nb.sphinx import (
    count_code_cells_by_language,
    expand_include_directives,
    filter_notebook_by_languages,
    get_cell_language,
    normalize_language_for_variant,
    split_code_fences_in_markdown_cells,
    strip_myst_directives_from_notebook,
)


class TestLanguageDetection:
    """Test language detection and normalization."""

    def test_get_cell_language_python(self):
        """Test Python code cell language detection."""
        cell = {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]}

        language = get_cell_language(cell)

        assert language == "python"

    def test_get_cell_language_bash(self):
        """Test bash code cell language detection."""
        cell = {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hello'"]}

        language = get_cell_language(cell)

        assert language == "bash"

    def test_get_cell_language_sh(self):
        """Test sh code cell language detection."""
        cell = {"cell_type": "code", "metadata": {"language": "sh"}, "source": ["ls -la"]}

        language = get_cell_language(cell)

        assert language == "sh"

    def test_get_cell_language_markdown(self):
        """Test markdown cell language detection."""
        cell = {"cell_type": "markdown", "source": ["# Title"]}

        language = get_cell_language(cell)

        assert language == "markdown"

    def test_get_cell_language_default_python(self):
        """Test default language is Python when not specified."""
        cell = {"cell_type": "code", "metadata": {}, "source": ["x = 1"]}

        language = get_cell_language(cell)

        assert language == "python"

    def test_normalize_language_python(self):
        """Test Python language normalization."""
        assert normalize_language_for_variant("python") == "python"

    def test_normalize_language_bash(self):
        """Test bash language normalization to CLI."""
        assert normalize_language_for_variant("bash") == "cli"

    def test_normalize_language_sh(self):
        """Test sh language normalization to CLI."""
        assert normalize_language_for_variant("sh") == "cli"

    def test_normalize_language_shell(self):
        """Test shell language normalization to CLI."""
        assert normalize_language_for_variant("shell") == "cli"


class TestCellCounting:
    """Test code cell counting by language."""

    def test_count_empty_notebook(self):
        """Test counting in empty notebook."""
        notebook = {"cells": []}

        counts = count_code_cells_by_language(notebook)

        assert counts == {}

    def test_count_only_markdown(self):
        """Test counting notebook with only markdown cells."""
        notebook = {
            "cells": [{"cell_type": "markdown", "source": ["# Title"]}, {"cell_type": "markdown", "source": ["Text"]}]
        }

        counts = count_code_cells_by_language(notebook)

        assert counts == {}

    def test_count_python_cells(self):
        """Test counting Python code cells."""
        notebook = {
            "cells": [
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["y = 2"]},
            ]
        }

        counts = count_code_cells_by_language(notebook)

        assert counts == {"python": 2}

    def test_count_bash_cells(self):
        """Test counting bash code cells."""
        notebook = {
            "cells": [
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hello'"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["ls"]},
            ]
        }

        counts = count_code_cells_by_language(notebook)

        assert counts == {"bash": 2}

    def test_count_mixed_languages(self):
        """Test counting mixed Python and bash cells."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hi'"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["y = 2"]},
                {"cell_type": "markdown", "source": ["Text"]},
                {"cell_type": "code", "metadata": {"language": "sh"}, "source": ["ls"]},
            ]
        }

        counts = count_code_cells_by_language(notebook)

        assert counts == {"python": 2, "bash": 1, "sh": 1}


class TestNotebookFiltering:
    """Test notebook filtering by language."""

    def test_filter_python_only(self):
        """Test filtering to keep only Python cells."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hi'"]},
                {"cell_type": "markdown", "source": ["Text"]},
            ]
        }

        filtered = filter_notebook_by_languages(notebook, {"python"})

        # Should keep markdown + python code cells
        assert len(filtered["cells"]) == 3
        assert filtered["cells"][0]["cell_type"] == "markdown"
        assert filtered["cells"][1]["cell_type"] == "code"
        assert filtered["cells"][1]["metadata"]["language"] == "python"
        assert filtered["cells"][2]["cell_type"] == "markdown"

    def test_filter_bash_only(self):
        """Test filtering to keep only bash cells."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hi'"]},
                {"cell_type": "markdown", "source": ["Text"]},
            ]
        }

        filtered = filter_notebook_by_languages(notebook, {"bash"})

        # Should keep markdown + bash code cells
        assert len(filtered["cells"]) == 3
        assert filtered["cells"][0]["cell_type"] == "markdown"
        assert filtered["cells"][1]["cell_type"] == "code"
        assert filtered["cells"][1]["metadata"]["language"] == "bash"
        assert filtered["cells"][2]["cell_type"] == "markdown"

    def test_filter_multiple_cli_languages(self):
        """Test filtering with multiple CLI languages."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hi'"]},
                {"cell_type": "code", "metadata": {"language": "sh"}, "source": ["ls"]},
                {"cell_type": "markdown", "source": ["Text"]},
            ]
        }

        filtered = filter_notebook_by_languages(notebook, {"bash", "sh", "shell"})

        # Should keep markdown + bash + sh code cells
        assert len(filtered["cells"]) == 4
        assert filtered["cells"][0]["cell_type"] == "markdown"
        assert filtered["cells"][1]["cell_type"] == "code"
        assert filtered["cells"][1]["metadata"]["language"] == "bash"
        assert filtered["cells"][2]["cell_type"] == "code"
        assert filtered["cells"][2]["metadata"]["language"] == "sh"
        assert filtered["cells"][3]["cell_type"] == "markdown"

    def test_filter_always_keeps_markdown(self):
        """Test that markdown cells are always kept regardless of filter."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "markdown", "source": ["## Section"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
            ]
        }

        # Filter for bash (which doesn't exist)
        filtered = filter_notebook_by_languages(notebook, {"bash"})

        # Should keep all markdown cells
        assert len(filtered["cells"]) == 2
        assert filtered["cells"][0]["cell_type"] == "markdown"
        assert filtered["cells"][1]["cell_type"] == "markdown"

    def test_filter_empty_result(self):
        """Test filtering when no code cells match."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
            ]
        }

        # Filter for bash (which doesn't exist)
        filtered = filter_notebook_by_languages(notebook, {"bash"})

        # Should keep only markdown cells
        assert len(filtered["cells"]) == 1
        assert filtered["cells"][0]["cell_type"] == "markdown"

    def test_filter_is_immutable(self):
        """Test that filtering returns a new dict without modifying original."""
        original = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["echo 'hi'"]},
            ]
        }

        filtered = filter_notebook_by_languages(original, {"python"})

        # Original should be unchanged
        assert len(original["cells"]) == 3
        # Filtered should have fewer cells
        assert len(filtered["cells"]) == 2


class TestMystDirectiveStripping:
    """Test MyST directive syntax removal from notebooks."""

    def test_strip_tab_set_directives(self):
        """Test removal of tab-set directive markers."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["::::{tab-set}\n"]},
                {"cell_type": "markdown", "source": ["# Title\n"]},
                {"cell_type": "markdown", "source": ["::::\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Tab-set directive cells should be removed
        assert len(cleaned["cells"]) == 1
        assert cleaned["cells"][0]["source"] == ["# Title"]

    def test_strip_tab_item_directives(self):
        """Test removal of tab-item directive markers."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": [":::{tab-item} CLI\n", ":sync: cli\n"]},
                {"cell_type": "markdown", "source": ["Content here\n"]},
                {"cell_type": "markdown", "source": [":::\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Directive cells should be removed, content should remain
        assert len(cleaned["cells"]) == 1
        assert cleaned["cells"][0]["source"] == ["Content here"]

    def test_strip_sync_tags(self):
        """Test removal of sync tags."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": [":::{tab-item} Python SDK\n", ":sync: python-sdk\n"]},
                {"cell_type": "markdown", "source": [":::\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Both cells should be removed (only directives)
        assert len(cleaned["cells"]) == 0

    def test_strip_mixed_content(self):
        """Test stripping directives while preserving content."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title\n", "\n", "Content line 1\n", "Content line 2\n"]},
                {"cell_type": "markdown", "source": [":::{tab-item} CLI\n", ":sync: cli\n"]},
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Should keep title/content cell and code cell, remove directive-only cell
        assert len(cleaned["cells"]) == 2
        assert cleaned["cells"][0]["cell_type"] == "markdown"
        assert "# Title" in cleaned["cells"][0]["source"][0]
        assert cleaned["cells"][1]["cell_type"] == "code"

    def test_preserve_code_cells(self):
        """Test that code cells are never modified."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {"language": "python"},
                    "source": ["# :sync: this-is-code\n", "x = 1\n"],
                },
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Code cells should be unchanged
        assert len(cleaned["cells"]) == 1
        assert cleaned["cells"][0]["source"] == ["# :sync: this-is-code\n", "x = 1\n"]

    def test_remove_empty_cells_after_stripping(self):
        """Test that cells with only directives are removed."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title\n"]},
                {"cell_type": "markdown", "source": [":::\n"]},
                {"cell_type": "markdown", "source": [":sync: cli\n"]},
                {"cell_type": "markdown", "source": ["Content\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Only title and content cells should remain
        assert len(cleaned["cells"]) == 2
        assert "# Title" in cleaned["cells"][0]["source"][0]
        assert "Content" in cleaned["cells"][1]["source"][0]

    def test_strip_option_tags(self):
        """Test removal of MyST option tags."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": [":class: my-class\n", ":name: my-name\n", "\n", "Content\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Option tags should be removed, content preserved
        assert len(cleaned["cells"]) == 1
        assert cleaned["cells"][0]["source"] == ["Content"]

    def test_strip_leading_trailing_blank_lines(self):
        """Test removal of leading/trailing blank lines after stripping."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["\n", "\n", "# Title\n", "\n", "Content\n", "\n", "\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Leading and trailing blank lines should be removed
        assert len(cleaned["cells"]) == 1
        source = "".join(cleaned["cells"][0]["source"])
        assert source.startswith("# Title")
        assert source.endswith("Content")

    def test_real_world_tab_set_example(self):
        """Test real-world tab-set pattern from deploy-models tutorial."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["::::{tab-set}\n"]},
                {"cell_type": "markdown", "source": [":::{tab-item} CLI\n", ":sync: cli\n"]},
                {"cell_type": "code", "metadata": {"language": "bash"}, "source": ["nemo models list\n"]},
                {"cell_type": "markdown", "source": [":::\n"]},
                {"cell_type": "markdown", "source": [":::{tab-item} Python SDK\n", ":sync: python-sdk\n"]},
                {
                    "cell_type": "code",
                    "metadata": {"language": "python"},
                    "source": ["client_from_platform(client, ModelsClient).list_models()\n"],
                },
                {"cell_type": "markdown", "source": [":::\n"]},
                {"cell_type": "markdown", "source": ["::::\n"]},
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Only code cells should remain (all directive cells removed)
        assert len(cleaned["cells"]) == 2
        assert all(cell["cell_type"] == "code" for cell in cleaned["cells"])

    def test_preserves_multi_item_list_structure(self):
        """Test that multi-item list sources preserve line boundaries."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Title\n",
                        "\n",
                        "Line 1\n",
                        "Line 2\n",
                        "Line 3\n",
                    ],
                }
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Should preserve multi-item list structure with keepends
        assert len(cleaned["cells"]) == 1
        source = cleaned["cells"][0]["source"]
        assert isinstance(source, list)
        assert len(source) == 5  # Each line preserved
        assert source[0] == "# Title\n"
        assert source[2] == "Line 1\n"

    def test_single_item_list_stays_simple(self):
        """Test that single-item lists or strings stay simple."""
        notebook = {"cells": [{"cell_type": "markdown", "source": ["# Title"]}]}

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Should keep as single-item list
        assert len(cleaned["cells"]) == 1
        source = cleaned["cells"][0]["source"]
        assert isinstance(source, list)
        assert len(source) == 1
        assert source[0] == "# Title"

    def test_preserves_include_directive(self):
        """Test that {include} directives are preserved (should be expanded by Sphinx)."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Title\n", "\n", "```{include} ../../_snippets/file.md\n", "```\n", "\n", "Content\n"],
                }
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Include directive should be preserved (Sphinx should expand it)
        assert len(cleaned["cells"]) == 1
        source = "".join(cleaned["cells"][0]["source"])
        assert "{include}" in source
        assert "# Title" in source
        assert "Content" in source

    def test_preserves_tip_directive(self):
        """Test that {tip} directives are preserved (should be rendered by Sphinx)."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "```{tip}\n",
                        "This is a helpful tip.\n",
                        "```\n",
                        "\n",
                        "Regular content\n",
                    ],
                }
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Tip directive should be preserved
        assert len(cleaned["cells"]) == 1
        source = "".join(cleaned["cells"][0]["source"])
        assert "{tip}" in source
        assert "Regular content" in source

    def test_preserves_note_directive(self):
        """Test that {note} directives are preserved (should be rendered by Sphinx)."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "Content before\n",
                        "\n",
                        "```{note}\n",
                        "Important note\n",
                        "```\n",
                        "\n",
                        "Content after\n",
                    ],
                }
            ]
        }

        cleaned = strip_myst_directives_from_notebook(notebook)

        # Note directive should be preserved
        assert len(cleaned["cells"]) == 1
        source = "".join(cleaned["cells"][0]["source"])
        assert "{note}" in source
        assert "Content before" in source
        assert "Content after" in source


class TestIncludeExpansion:
    """Test {include} directive expansion."""

    def test_expand_include_directive(self, tmp_path):
        """Test that {include} directives are expanded with actual file content."""
        # Create an included file
        snippet_dir = tmp_path / "snippets"
        snippet_dir.mkdir()
        snippet_file = snippet_dir / "setup.md"
        snippet_file.write_text("# Setup\n\nThis is the included content.\n")

        # Create notebook with include directive
        notebook_path = tmp_path / "tutorial.ipynb"
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Title\n",
                        "\n",
                        "```{include} snippets/setup.md\n",
                        "```\n",
                        "\n",
                        "More content\n",
                    ],
                }
            ]
        }

        expanded = expand_include_directives(notebook, notebook_path)

        # Include directive should be replaced with file content
        assert len(expanded["cells"]) == 1
        source = "".join(expanded["cells"][0]["source"])
        assert "{include}" not in source
        assert "# Setup" in source
        assert "This is the included content" in source
        assert "More content" in source

    def test_expand_multiple_includes(self, tmp_path):
        """Test expanding multiple {include} directives in one cell."""
        # Create included files
        snippet1 = tmp_path / "snippet1.md"
        snippet1.write_text("Content from snippet 1\n")
        snippet2 = tmp_path / "snippet2.md"
        snippet2.write_text("Content from snippet 2\n")

        notebook_path = tmp_path / "tutorial.ipynb"
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Title\n",
                        "\n",
                        "```{include} snippet1.md\n",
                        "```\n",
                        "\n",
                        "Middle content\n",
                        "\n",
                        "```{include} snippet2.md\n",
                        "```\n",
                        "\n",
                        "End\n",
                    ],
                }
            ]
        }

        expanded = expand_include_directives(notebook, notebook_path)

        # Both includes should be expanded
        assert len(expanded["cells"]) == 1
        source = "".join(expanded["cells"][0]["source"])
        assert "{include}" not in source
        assert "Content from snippet 1" in source
        assert "Content from snippet 2" in source
        assert "Middle content" in source

    def test_missing_include_file_logs_warning(self, tmp_path):
        """Test that missing include files are handled gracefully."""
        notebook_path = tmp_path / "tutorial.ipynb"
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Title\n",
                        "\n",
                        "```{include} nonexistent.md\n",
                        "```\n",
                        "\n",
                        "Content\n",
                    ],
                }
            ]
        }

        # Should not raise an error, just log a warning
        expanded = expand_include_directives(notebook, notebook_path)

        # Include directive should remain since file wasn't found
        assert len(expanded["cells"]) == 1
        source = "".join(expanded["cells"][0]["source"])
        assert "{include}" in source or "nonexistent.md" in source

    def test_preserves_code_cells_during_expansion(self, tmp_path):
        """Test that code cells are never modified during include expansion."""
        snippet = tmp_path / "snippet.md"
        snippet.write_text("Included content\n")

        notebook_path = tmp_path / "tutorial.ipynb"
        notebook = {
            "cells": [
                {"cell_type": "code", "metadata": {"language": "python"}, "source": ["x = 1\n"]},
                {
                    "cell_type": "markdown",
                    "source": [
                        "```{include} snippet.md\n",
                        "```\n",
                    ],
                },
            ]
        }

        expanded = expand_include_directives(notebook, notebook_path)

        # Code cell should be unchanged
        assert len(expanded["cells"]) == 2
        assert expanded["cells"][0]["source"] == ["x = 1\n"]
        # Markdown cell should have include expanded
        source = "".join(expanded["cells"][1]["source"])
        assert "Included content" in source

    def test_relative_include_paths(self, tmp_path):
        """Test that relative paths are resolved correctly."""
        # Create nested directory structure
        tutorials_dir = tmp_path / "tutorials"
        tutorials_dir.mkdir()
        snippets_dir = tmp_path / "snippets"
        snippets_dir.mkdir()

        snippet_file = snippets_dir / "setup.md"
        snippet_file.write_text("Setup instructions\n")

        notebook_path = tutorials_dir / "tutorial.ipynb"
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "```{include} ../snippets/setup.md\n",
                        "```\n",
                    ],
                }
            ]
        }

        expanded = expand_include_directives(notebook, notebook_path)

        # Include should be resolved relative to notebook
        assert len(expanded["cells"]) == 1
        source = "".join(expanded["cells"][0]["source"])
        assert "Setup instructions" in source

    def test_expand_include_with_generated_notebook_path(self, tmp_path):
        """Test include expansion when notebook is in _generated/nemo-nb/ subdir.

        The include path is relative to the source file location, not the
        generated notebook location.
        """
        # Simulate: docs/_snippets/tutorials/cli-sdk-setup.md
        snippet_dir = tmp_path / "_snippets" / "tutorials"
        snippet_dir.mkdir(parents=True)
        snippet_file = snippet_dir / "cli-sdk-setup.md"
        snippet_file.write_text("# Setup\n\nSDK setup content.\n")

        # Simulate: docs/_generated/nemo-nb/run-inference/tutorials/deploy-models.ipynb
        # (but include path written relative to docs/run-inference/tutorials/)
        generated_dir = tmp_path / "_generated" / "nemo-nb" / "run-inference" / "tutorials"
        generated_dir.mkdir(parents=True)

        # source_equiv_path = tmp_path / "run-inference/tutorials/deploy-models.ipynb"
        # so ../../_snippets/tutorials/cli-sdk-setup.md resolves correctly.
        # The source directory must exist for OS-level .. traversal to work.
        source_equiv_dir = tmp_path / "run-inference" / "tutorials"
        source_equiv_dir.mkdir(parents=True)
        source_equiv_path = source_equiv_dir / "deploy-models.ipynb"

        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Deploy Models\n",
                        "\n",
                        "```{include} ../../_snippets/tutorials/cli-sdk-setup.md\n",
                        "```\n",
                        "\n",
                        "## Next Section\n",
                    ],
                }
            ]
        }

        # Pass source_equiv_path (not notebook_path) to get correct resolution
        expanded = expand_include_directives(notebook, source_equiv_path)

        source = "".join(expanded["cells"][0]["source"])
        assert "{include}" not in source
        assert "SDK setup content" in source
        assert "## Next Section" in source


class TestSplitCodeFencesInMarkdownCells:
    """Test promotion of code fences inside markdown cells to real code cells."""

    def _md_cell(self, text: str) -> dict:
        return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}

    def _code_cell(self, lang: str, text: str) -> dict:
        return {
            "cell_type": "code",
            "metadata": {"language": lang},
            "source": text.splitlines(keepends=True),
            "outputs": [],
            "execution_count": None,
        }

    def test_promotes_bash_block_to_code_cell(self):
        """A bash code fence inside a markdown cell becomes a code cell."""
        notebook = {"cells": [self._md_cell("Some text\n\n```bash\nnemo install\n```\n\nMore text\n")]}
        result = split_code_fences_in_markdown_cells(notebook)
        cell_types = [c["cell_type"] for c in result["cells"]]
        assert "code" in cell_types
        code_cell = next(c for c in result["cells"] if c["cell_type"] == "code")
        assert "nemo install" in "".join(code_cell["source"])
        assert code_cell["metadata"]["language"] == "bash"

    def test_colon_fenced_tabset_with_bash_and_python(self):
        """Simulates the cli-sdk-setup.md snippet: colon-fenced tab-set containing
        bash and python blocks.  Both blocks must become code cells."""
        snippet_content = (
            "::::{tab-set}\n\n"
            ":::{tab-item} CLI\n:sync: cli\n\n"
            "```bash\nnemo config set --base-url $URL\n```\n\n"
            ":::\n\n"
            ":::{tab-item} Python SDK\n:sync: python-sdk\n\n"
            "```python\nimport os\n```\n\n"
            ":::\n\n::::\n"
        )
        notebook = {"cells": [self._md_cell(snippet_content)]}
        result = split_code_fences_in_markdown_cells(notebook)

        code_cells = [c for c in result["cells"] if c["cell_type"] == "code"]
        languages = {c["metadata"]["language"] for c in code_cells}
        assert "bash" in languages
        assert "python" in languages

    def test_leaves_directive_fences_alone(self):
        """```{note} directive fences must NOT be promoted to code cells."""
        notebook = {"cells": [self._md_cell("```{note}\nThis is a note.\n```\n")]}
        result = split_code_fences_in_markdown_cells(notebook)
        assert len(result["cells"]) == 1
        assert result["cells"][0]["cell_type"] == "markdown"

    def test_plain_code_cells_untouched(self):
        """Existing code cells are passed through unchanged."""
        notebook = {
            "cells": [
                self._code_cell("python", "x = 1\n"),
                self._md_cell("Prose\n"),
            ]
        }
        result = split_code_fences_in_markdown_cells(notebook)
        assert len(result["cells"]) == 2
        assert result["cells"][0]["cell_type"] == "code"
        assert "".join(result["cells"][0]["source"]) == "x = 1\n"

    def test_end_to_end_include_then_split(self, tmp_path):
        """Full pipeline: expand {include} then split → code cells are executable."""
        snippet = tmp_path / "setup.md"
        snippet.write_text(
            "::::{tab-set}\n\n"
            ":::{tab-item} CLI\n:sync: cli\n\n"
            "```bash\nnemo config set\n```\n\n"
            ":::\n\n"
            ":::{tab-item} Python\n:sync: python\n\n"
            "```python\nimport nemo\n```\n\n"
            ":::\n\n::::\n"
        )
        notebook_path = tmp_path / "tutorial.ipynb"
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Title\n",
                        "\n",
                        "```{include} setup.md\n",
                        "```\n",
                    ],
                }
            ]
        }

        expanded = expand_include_directives(notebook, notebook_path)
        final = split_code_fences_in_markdown_cells(expanded)

        code_cells = [c for c in final["cells"] if c["cell_type"] == "code"]
        langs = {c["metadata"]["language"] for c in code_cells}
        assert "bash" in langs, f"Expected bash code cell, got cell types: {[c['cell_type'] for c in final['cells']]}"
        assert "python" in langs
