#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 FILELIST" >&2
    exit 2
fi

filelist="$1"
if [ ! -f "${filelist}" ]; then
    echo "missing file list: ${filelist}" >&2
    exit 1
fi

failed=0

while IFS= read -r path || [ -n "${path}" ]; do
    path="${path%$'\r'}"
    case "${path}" in
        ""|\#*)
            continue
            ;;
        /*)
            ;;
        *)
            echo "cleanup path must be absolute: ${path}" >&2
            failed=1
            continue
            ;;
    esac

    if ! rm -f -- "${path}"; then
        echo "failed to remove listed file: ${path}" >&2
        failed=1
        continue
    fi

    if [ -e "${path}" ] || [ -L "${path}" ]; then
        echo "listed file remains after cleanup: ${path}" >&2
        failed=1
    fi
done < "${filelist}"

exit "${failed}"
