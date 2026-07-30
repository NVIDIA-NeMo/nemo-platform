#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_ROOT="${1:-${PLUGIN_ROOT}/tmp/tau3-airline-smoke}"
SOURCE_ROOT="${OUTPUT_ROOT}/source"
DATASET_ROOT="${SOURCE_ROOT}/tau3-bench"
TRAIN_ROOT="${OUTPUT_ROOT}/train"
VALIDATION_ROOT="${OUTPUT_ROOT}/validation"
DATASET_REF="sierra-research/tau3-bench@1"

TRAIN_TASKS=(
  "tau3-bench__tau3-airline-0"
  "tau3-bench__tau3-airline-20"
  "tau3-bench__tau3-airline-39"
)
VALIDATION_TASKS=(
  "tau3-bench__tau3-airline-3"
  "tau3-bench__tau3-airline-36"
)

if [[ ! -f "${DATASET_ROOT}/${TRAIN_TASKS[0]}/task.toml" ]]; then
  mkdir -p "${SOURCE_ROOT}"
  (
    cd "${PLUGIN_ROOT}"
    uv run --frozen harbor download "${DATASET_REF}" \
      --output-dir "${SOURCE_ROOT}" \
      --export \
      --overwrite
  )
fi

prepare_split() {
  local split_root="$1"
  shift
  local task_names=("$@")

  if [[ -d "${split_root}" ]]; then
    local existing_tasks=("${split_root}"/*/task.toml)
    if [[ ${#existing_tasks[@]} -eq ${#task_names[@]} ]]; then
      for task_name in "${task_names[@]}"; do
        if [[ ! -f "${split_root}/${task_name}/task.toml" ]]; then
          echo "Existing split is not the expected dataset: ${split_root}" >&2
          exit 1
        fi
      done
      echo "Reusing ${split_root}"
      return
    fi
    echo "Existing split is incomplete: ${split_root}" >&2
    exit 1
  fi

  mkdir -p "${split_root}"
  for task_name in "${task_names[@]}"; do
    local source_task="${DATASET_ROOT}/${task_name}"
    if [[ ! -f "${source_task}/task.toml" ]]; then
      echo "Downloaded dataset is missing ${task_name}" >&2
      exit 1
    fi
    cp -R "${source_task}" "${split_root}/${task_name}"
  done
}

prepare_split "${TRAIN_ROOT}" "${TRAIN_TASKS[@]}"
prepare_split "${VALIDATION_ROOT}" "${VALIDATION_TASKS[@]}"

echo "Tau3 Airline smoke datasets are ready:"
echo "  train:      ${TRAIN_ROOT}"
echo "  validation: ${VALIDATION_ROOT}"
