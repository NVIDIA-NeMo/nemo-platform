# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test env for scaled-evals Settings import (must run before package imports)."""

from __future__ import annotations

import base64
import os

# Each test module guards its own imports, rather than this conftest ignoring the directory:
# a `collect_ignore_glob` here behaved as intended in a standalone reproduction but did not
# take effect in the repo-wide CI run, and per-module skips do not depend on that mechanism.
#
# conftest runs before any of those per-module guards, so it must import nothing the plugin
# brings in. A Fernet key is 32 random bytes in urlsafe base64, which is why this builds one
# from the standard library rather than calling Fernet.generate_key().

# Settings() is constructed at import time and requires a valid Fernet key.
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
os.environ.setdefault("DATABASE_SSL_MODE", "disable")
os.environ.setdefault("CONTROL_PLANE_AUTH_ENABLED", "false")
