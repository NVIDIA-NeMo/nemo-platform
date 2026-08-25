# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test env for scaled-evals Settings import (must run before package imports)."""

from __future__ import annotations

import importlib.util
import os

from cryptography.fernet import Fernet

# This plugin is a workspace member but is deliberately absent from `enabled-plugins`, so
# a plain `uv sync` leaves it uninstalled and these modules unimportable. Skip instead of
# erroring at collection: the repo-wide unit run sweeps this directory, while the job that
# owns these tests installs the `scaled-evals` dependency group first.
if any(importlib.util.find_spec(m) is None for m in ("scaled_evals", "psycopg", "psycopg_pool")):
    collect_ignore_glob = ["*.py"]

# Settings() is constructed at import time and requires a valid Fernet key.
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_SSL_MODE", "disable")
os.environ.setdefault("CONTROL_PLANE_AUTH_ENABLED", "false")
