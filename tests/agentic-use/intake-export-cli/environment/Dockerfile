# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

FROM nmp-agentic-base:latest

# Disable MCP by removing the MCP configuration file
# This forces Claude Code to use the CLI instead of MCP tools
RUN rm -f /app/.mcp.json

# Enable the Intake service in the platform config.
# It is commented out by default in the quickstart, but this eval requires it.
# Uncomment in AVAILABLE_SERVICES dict and API_SERVICES list.
RUN sed -i 's/# "intake": "nmp.intake.main:service"/"intake": "nmp.intake.main:service"/' /app/packages/nmp_platform/src/nmp/platform/config.py && \
    sed -i 's/# "intake",/"intake",/' /app/packages/nmp_platform/src/nmp/platform/config.py
