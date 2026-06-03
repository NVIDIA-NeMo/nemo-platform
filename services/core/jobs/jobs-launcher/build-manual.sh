#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jobs-launcher"
GOOS=${1:-linux}
GOARCH=${2:-amd64}

echo "Building static binary for ${APP_NAME}..."

# Warning: this binary is copied by the Docker jobs controller into the target
# job container at /jobs-launcher. The current Docker backend assumes the
# launcher matches the target job container OS/arch. Build it for the target
# container platform, not for the controller host platform. Cross-arch only
# works when the runtime has emulation configured (for example binfmt/QEMU).

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
