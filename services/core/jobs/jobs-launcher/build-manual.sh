#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

APP_NAME="jobs-launcher"
GOOS=${1:-linux}
GOARCH=${2:-amd64}

echo "Building static binary for ${APP_NAME}..."

# Use -trimpath and disable CGO for a fully static binary
CGO_ENABLED=0 GOOS=${GOOS} GOARCH=${GOARCH} go build \
    -a \
    -installsuffix cgo \
    -ldflags="-s -w -extldflags '-static'" \
    -trimpath \
    -o "${APP_NAME}" \
    ./main.go

echo "Build complete: ${APP_NAME}"
ls -lh "${APP_NAME}"
