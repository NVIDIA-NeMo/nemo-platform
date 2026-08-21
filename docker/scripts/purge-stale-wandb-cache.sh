#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Drop every uv-cache wandb artifact that is not the pinned version.
#
# NeMo-RL's lock still resolves wandb 0.28.1. That wheel's wandb-core has
# GHSA-hrxh-6v49-42gf (google.golang.org/grpc < 1.82.1) and GO-2026-5970
# (golang.org/x/text < 0.39.0). Installing 0.28.2 into venvs is not enough:
# scanners walk /opt/uv_cache and report the leftover 0.28.1 wheel/archive.

set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "usage: $0 KEEP_VERSION [CACHE_DIR]" >&2
    exit 2
fi

keep="$1"
cache="${2:-${UV_CACHE_DIR:-}}"
if [ -z "${cache}" ]; then
    echo "CACHE_DIR or UV_CACHE_DIR is required" >&2
    exit 2
fi
if [ ! -d "${cache}" ]; then
    echo "uv cache directory does not exist: ${cache}" >&2
    exit 1
fi

is_keep_artifact() {
    case "$1" in
        "wandb-${keep}.dist-info" | "wandb-${keep}.tar.gz" | "wandb-${keep}-"*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

if [ -d "${cache}/archive-v0" ]; then
    shopt -s nullglob
    for d in "${cache}"/archive-v0/*/; do
        dist_infos=("${d}"wandb-*.dist-info)
        if [ "${#dist_infos[@]}" -eq 0 ]; then
            continue
        fi
        keep_dist=0
        for info in "${dist_infos[@]}"; do
            if is_keep_artifact "$(basename "${info}")"; then
                keep_dist=1
            fi
        done
        if [ "${keep_dist}" -eq 0 ]; then
            rm -rf "${d}"
        fi
    done
    shopt -u nullglob
fi

while IFS= read -r -d '' artifact; do
    if is_keep_artifact "$(basename "${artifact}")"; then
        continue
    fi
    rm -rf "${artifact}"
done < <(
    find "${cache}" \( \
        -name 'wandb-*.whl' -o \
        -name 'wandb-*.tar.gz' -o \
        -name 'wandb-*.dist-info' \
        \) -print0 2>/dev/null
)

stale="$(
    find "${cache}" \( \
        -name 'wandb-*.whl' -o \
        -name 'wandb-*.tar.gz' -o \
        -name 'wandb-*.dist-info' \
        \) -print 2>/dev/null | while IFS= read -r artifact; do
        is_keep_artifact "$(basename "${artifact}")" && continue
        printf '%s\n' "${artifact}"
    done
)"
if [ -n "${stale}" ]; then
    echo "ERROR: stale wandb artifacts remain in ${cache}:" >&2
    printf '%s\n' "${stale}" >&2
    exit 1
fi
