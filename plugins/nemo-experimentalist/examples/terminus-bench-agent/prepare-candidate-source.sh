#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 HARBOR_CHECKOUT DESTINATION" >&2
  exit 2
fi

harbor_checkout=$(realpath "$1")
destination=$2
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ ! -f "$harbor_checkout/src/harbor/agents/terminus_2/terminus_2.py" ]]; then
  echo "not a Harbor checkout: $harbor_checkout" >&2
  exit 2
fi
if [[ -e "$destination" ]]; then
  echo "destination already exists; choose a fresh path: $destination" >&2
  exit 2
fi

mkdir -p -- "$destination"
rsync -a \
  --exclude=/.git/ \
  --exclude=/.venv/ \
  --exclude=/jobs/ \
  --exclude=/trials/ \
  --exclude='__pycache__/' \
  "$harbor_checkout/" "$destination/"
cp -- "$script_dir/harbor_wrapper.py" "$destination/harbor_wrapper.py"

echo "$destination"
