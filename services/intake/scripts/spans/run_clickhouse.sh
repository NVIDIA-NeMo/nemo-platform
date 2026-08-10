#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../../.." && pwd)"
clickhouse_version="$(tr -d '[:space:]' < "${script_dir}/../../.clickhouse-version")"

# Preserve the script's historical credential overrides while delegating all
# lifecycle, identity, port allocation, and readiness logic to Intake's Python
# provisioner.
export NMP_INTAKE_CLICKHOUSE_USER="${NMP_INTAKE_CLICKHOUSE_USER:-${CLICKHOUSE_USER:-default}}"
export NMP_INTAKE_CLICKHOUSE_PASSWORD="${NMP_INTAKE_CLICKHOUSE_PASSWORD:-${CLICKHOUSE_PASSWORD:-}}"
export NMP_INTAKE_CLICKHOUSE_IMAGE="${NMP_INTAKE_CLICKHOUSE_IMAGE:-${CLICKHOUSE_IMAGE:-clickhouse/clickhouse-server:${clickhouse_version}}}"
export NMP_INTAKE_CLICKHOUSE_DATA_DIR="${NMP_INTAKE_CLICKHOUSE_DATA_DIR:-${CLICKHOUSE_DATA_DIR:-${repo_root}/tmp/intake-clickhouse}}"

cd "${repo_root}"
exec uv run python -m nmp.intake.local_clickhouse --legacy-script-mode "$@"
