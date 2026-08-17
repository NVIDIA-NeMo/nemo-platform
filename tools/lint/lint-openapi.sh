#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
# Verify OpenAPI specs are up to date by regenerating and diffing.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"

check_dir="openapicheck"
rm -rf "${check_dir}"
mkdir -p "${check_dir}"

mapfile -t spec_files < <(git ls-files 'openapi/**/*.yaml' 'openapi/*.yaml' 'plugins/*/openapi/openapi.yaml')
for spec_file in "${spec_files[@]}"; do
    mkdir -p "${check_dir}/$(dirname "${spec_file}")"
    cp "${spec_file}" "${check_dir}/${spec_file}"
done

script/generate-openapi-spec.sh

for spec_file in "${spec_files[@]}"; do
    diff "${check_dir}/${spec_file}" "${spec_file}"
done

new_plugin_specs="$(git ls-files --others --exclude-standard 'plugins/*/openapi/openapi.yaml')"
if [[ -n "${new_plugin_specs}" ]]; then
    echo "New plugin OpenAPI specs were generated and must be committed:" >&2
    echo "${new_plugin_specs}" >&2
    exit 1
fi
