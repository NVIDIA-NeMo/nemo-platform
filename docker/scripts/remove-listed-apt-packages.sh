#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 PACKAGE_LIST" >&2
    exit 2
fi

package_list="$1"
if [ ! -f "${package_list}" ]; then
    echo "missing package list: ${package_list}" >&2
    exit 1
fi

packages=()

while IFS= read -r package || [ -n "${package}" ]; do
    package="${package%$'\r'}"
    package="${package%%#*}"
    package="$(printf '%s' "${package}" | xargs)"

    if [ -z "${package}" ]; then
        continue
    fi

    if dpkg-query -W -f='${db:Status-Abbrev}' "${package}" 2>/dev/null | grep -q '^ii '; then
        packages+=("${package}")
    fi
done < "${package_list}"

if [ "${#packages[@]}" -eq 0 ]; then
    exit 0
fi

DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}" apt-get purge -y "${packages[@]}"
