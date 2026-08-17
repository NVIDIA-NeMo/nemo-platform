# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Use the pre-built nmp-agentic-base image
# Build the base image first with: docker build -f Dockerfile.agentic-base -t nmp-agentic-base:latest .
FROM nmp-agentic-base:latest

# Disable MCP to force CLI usage
RUN rm -f /app/.mcp.json
