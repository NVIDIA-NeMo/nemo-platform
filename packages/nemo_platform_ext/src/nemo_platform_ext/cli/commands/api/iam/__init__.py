# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from importlib import import_module as _importlib_import_module

from nemo_platform_ext.cli.core.help_formatter import create_typer_app

_cli_child_role_bindings = _importlib_import_module("nemo_platform_ext.cli.commands.api.iam.role_bindings")

app = create_typer_app(name="iam", help="Iam operations")

app.add_typer(_cli_child_role_bindings.app, name="role-bindings")
