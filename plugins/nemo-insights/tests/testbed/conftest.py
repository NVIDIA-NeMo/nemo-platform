# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Make the `testbed` package importable for its tests.

`testbed/` is maintainer tooling at the repo root (not shipped under `src/`), so its
tests import `testbed.*` and need the repo root on `sys.path`. Scoped here — to the
testbed tests only — rather than widening the global `pythonpath` in pyproject.toml.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
