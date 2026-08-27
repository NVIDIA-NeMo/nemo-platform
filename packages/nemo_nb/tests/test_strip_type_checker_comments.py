# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for stripping type checker comments from code cells."""

import pytest
from nemo_nb.converter import NotebookConverter


def test_strip_ty_ignore_comments():
    """Test that ty: ignore comments are stripped from code cells."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"language": "python"},
                "source": [
                    "# This is a regular comment\n",
                    "client_from_platform(sdk, ModelsClient).get_openai_route_base_url()\n",
                    "client_from_platform(sdk, ModelsClient).get_model_entity_route_openai_url(entity) # ty: ignore[unresolved-reference]\n",
                    "client_from_platform(sdk, ModelsClient).get_provider_route_openai_url(provider) # ty: ignore[unresolved-reference]\n",
                ],
            }
        ]
    }

    converter = NotebookConverter()
    result = converter.convert_notebook_dict(notebook)

    # Verify that ty: comments are removed
    assert "# ty: ignore" not in result
    assert "# ty:" not in result

    # Verify that regular comments are preserved
    assert "# This is a regular comment" in result

    # Verify that the code lines are still there (without the ty: comments)
    assert "client_from_platform(sdk, ModelsClient).get_model_entity_route_openai_url(entity)" in result
    assert "client_from_platform(sdk, ModelsClient).get_provider_route_openai_url(provider)" in result


def test_strip_type_ignore_comments():
    """Test that type: ignore comments are also stripped."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"language": "python"},
                "source": [
                    "result = some_function()  # type: ignore[arg-type]\n",
                    "another_call()  # type: ignore\n",
                ],
            }
        ]
    }

    converter = NotebookConverter()
    result = converter.convert_notebook_dict(notebook)

    # Verify that type: ignore comments are removed
    assert "# type: ignore" not in result


def test_preserve_code_without_type_comments():
    """Test that code without type checker comments is unchanged."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"language": "python"},
                "source": [
                    "# Normal comment\n",
                    "x = 1  # inline comment\n",
                    "y = 2\n",
                ],
            }
        ]
    }

    converter = NotebookConverter()
    result = converter.convert_notebook_dict(notebook)

    # Verify that normal comments are preserved
    assert "# Normal comment" in result
    assert "# inline comment" in result


def test_strip_multiple_ty_patterns():
    """Test that various ty: comment patterns are stripped."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"language": "python"},
                "source": [
                    "line1()  # ty: ignore[misc]\n",
                    "line2()  # ty: ignore\n",
                    "line3()  # ty:ignore[something]\n",
                ],
            }
        ]
    }

    converter = NotebookConverter()
    result = converter.convert_notebook_dict(notebook)

    # Verify all patterns are removed
    assert "# ty:" not in result
    assert "ty: ignore" not in result
    assert "ty:ignore" not in result


def test_strip_comments_preserves_trailing_whitespace_behavior():
    """Test that stripping comments doesn't add or remove unexpected whitespace."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"language": "python"},
                "source": [
                    "function_call(arg1, arg2)  # ty: ignore[unresolved-reference]\n",
                ],
            }
        ]
    }

    converter = NotebookConverter()
    result = converter.convert_notebook_dict(notebook)

    # The line should end cleanly without the comment
    # Check that the function call is present and clean
    assert "function_call(arg1, arg2)" in result
    # And that there's no trailing comment marker
    assert "# ty:" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
