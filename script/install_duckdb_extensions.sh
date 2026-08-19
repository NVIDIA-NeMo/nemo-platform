#!/usr/bin/env sh
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Preseed DuckDB extensions into the local cache for container images.
set -eu

PYTHON_BIN="${PYTHON_BIN:-/app/.venv/bin/python}"
DUCKDB_HOME="${DUCKDB_HOME:-/root}"
EXTENSIONS="${DUCKDB_EXTENSIONS:-httpfs aws}"
TMP_DIR="${DUCKDB_TMP_DIR:-/tmp/duckdb-extensions}"

cleanup() {
    rm -f "$TMP_DIR"/*.duckdb_extension
    rmdir "$TMP_DIR" 2>/dev/null || true
}

trap cleanup EXIT

arch="$(uname -m)"
case "$arch" in
    arm64|aarch64)
        duckdb_platform="linux_arm64"
        ;;
    x86_64|amd64)
        duckdb_platform="linux_amd64"
        ;;
    *)
        echo "Unsupported DuckDB platform architecture: $arch" >&2
        exit 1
        ;;
esac

duckdb_version="$("$PYTHON_BIN" -c "import duckdb; print(duckdb.__version__)")"
mkdir -p "$TMP_DIR"

for extension in $EXTENSIONS; do
    extension_file="${TMP_DIR}/${extension}.duckdb_extension"
    extension_url="https://extensions.duckdb.org/v${duckdb_version}/${duckdb_platform}/${extension}.duckdb_extension.gz"
    curl -fsSL "$extension_url" | gzip -d > "$extension_file"
done

HOME="$DUCKDB_HOME" DUCKDB_TMP_DIR="$TMP_DIR" "$PYTHON_BIN" -c "
import duckdb
import os

conn = duckdb.connect()
for ext in '${EXTENSIONS}'.split():
    ext_path = os.path.join(os.environ['DUCKDB_TMP_DIR'], f'{ext}.duckdb_extension')
    conn.execute(f\"INSTALL '{ext_path}'\")
    conn.execute(f'LOAD {ext}')
conn.close()
"
