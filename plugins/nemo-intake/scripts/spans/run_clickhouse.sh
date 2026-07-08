#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

container_name="nemo-intake-plugin-clickhouse"
legacy_container_names=("nmp-intake-clickhouse" "nemo-intake-clickhouse")
image="${CLICKHOUSE_IMAGE:-clickhouse/clickhouse-server:24.3}"
clickhouse_user="${CLICKHOUSE_USER:-default}"
clickhouse_password="${CLICKHOUSE_PASSWORD:-}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../../.." && pwd)"
data_dir="${CLICKHOUSE_DATA_DIR:-${repo_root}/tmp/intake-clickhouse}"

ensure_host_dirs() {
  mkdir -p "${data_dir}/tmp"
  chmod 755 "${data_dir}" "${data_dir}/tmp"
}

ensure_tmp_dir() {
  docker exec "$1" sh -c "mkdir -p /var/lib/clickhouse/tmp && chown clickhouse:clickhouse /var/lib/clickhouse/tmp" >/dev/null
}

if docker ps --filter "name=^/${container_name}$" --filter "status=running" --format "{{.Names}}" | grep -qx "${container_name}"; then
  ensure_tmp_dir "${container_name}"
  echo "${container_name} is already running"
  exit 0
fi

for legacy_container_name in "${legacy_container_names[@]}"; do
  if docker ps --filter "name=^/${legacy_container_name}$" --filter "status=running" --format "{{.Names}}" | grep -qx "${legacy_container_name}"; then
    ensure_tmp_dir "${legacy_container_name}"
    echo "${legacy_container_name} is already running; reusing it for Intake ClickHouse"
    exit 0
  fi
done

if docker ps -a --filter "name=^/${container_name}$" --format "{{.Names}}" | grep -qx "${container_name}"; then
  ensure_host_dirs
  docker start "${container_name}" >/dev/null
  ensure_tmp_dir "${container_name}"
  echo "${container_name} started"
  exit 0
fi

ensure_host_dirs
docker run -d \
  --name "${container_name}" \
  -e CLICKHOUSE_USER="${clickhouse_user}" \
  -e CLICKHOUSE_PASSWORD="${clickhouse_password}" \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 \
  -e CLICKHOUSE_SKIP_USER_SETUP=1 \
  -p 8123:8123 \
  -p 9000:9000 \
  -v "${data_dir}:/var/lib/clickhouse" \
  "${image}" >/dev/null

ensure_tmp_dir "${container_name}"
echo "${container_name} created and started with data dir ${data_dir}"
