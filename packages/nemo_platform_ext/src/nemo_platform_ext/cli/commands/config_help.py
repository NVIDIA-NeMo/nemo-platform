# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared help text for the config command group."""

CONFIG_APP_HELP = """\
Manage NeMo Platform CLI configuration.

Examples:
# Connect the current context to a remote deployment.
nemo config set --base-url https://nmp.example.com
# Keep contexts separate.
nemo config set --context staging --base-url https://nmp.staging.example.com
nemo config set --context production --base-url https://nmp.example.com --activate
# Switch the current context and inspect its configuration.
nemo config use-context staging
nemo config view

NMP_BASE_URL and NMP_CURRENT_CONTEXT override saved configuration."""
