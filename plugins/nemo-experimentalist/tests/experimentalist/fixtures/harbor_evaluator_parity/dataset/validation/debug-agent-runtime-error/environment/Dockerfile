# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Intentional failure fixture: WrappedAgent uploads the source successfully, but
# `python main.py` fails with exit code 127 because this image has no Python.

FROM debian:bookworm-slim

WORKDIR /app

RUN mkdir -p /app/artifacts /app/traces
