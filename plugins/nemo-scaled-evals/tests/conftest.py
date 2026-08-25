# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test env for scaled-evals Settings import (must run before package imports)."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

# Each test module guards its own imports, rather than this conftest ignoring the directory:
# a `collect_ignore_glob` here behaved as intended in a standalone reproduction but did not
# take effect in the repo-wide CI run, and per-module skips do not depend on that mechanism.

# Settings() is constructed at import time and requires a valid Fernet key.
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_SSL_MODE", "disable")
os.environ.setdefault("CONTROL_PLANE_AUTH_ENABLED", "false")
