# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Top-level conftest: runs before any test module is imported.

Eval Author and Experimentalist agents call get_smart_model() at class-definition
time. Placeholder credentials keep collection working when real keys are absent.
setdefault does not overwrite CI or developer-provided values.

Both stand-in values contain "placeholder" on purpose: real-model canaries such as
test_eval_author_repair_e2e cannot use "is it set?" to decide whether to skip, because
these assignments make every credential look present. Keep the substring if you change
the values.
"""

import os

import litellm
import pytest

# An unroutable HTTPS host: if a real key is present but the base is not, an
# unmocked call fails to connect rather than sending the key over plaintext.
os.environ.setdefault("AUTHOR_API_BASE", "https://placeholder.invalid")
os.environ.setdefault("AUTHOR_API_KEY", "placeholder-for-import")
os.environ.setdefault("EXPERIMENTALIST_API_BASE", "https://placeholder.invalid")
os.environ.setdefault("EXPERIMENTALIST_API_KEY", "placeholder-for-import")

litellm.drop_params = True


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes that monkeypatch cannot restore."""
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
