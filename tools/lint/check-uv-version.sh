#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

_python_ver="$(yq '.tool.uv.required-version' pyproject.toml)"
_flox_ver="$(yq '.install.uv.version' flox-environments/python/.flox/env/manifest.toml)"

if [[ "${_python_ver}" != "${_flox_ver}" ]]; then
  printf "uv version constraints differ:\n\n"
  printf "pyproject.toml flox-env\n%s %s\n" "${_python_ver}" "${_flox_ver}" | column -t
  exit 1
fi
