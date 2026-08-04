#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_ROOT="${1:-${PLUGIN_ROOT}/tmp/tau3-airline}"
SOURCE_ROOT="${OUTPUT_ROOT}/source"
DATASET_ROOT="${SOURCE_ROOT}/tau3-bench"
INSIGHTS_ROOT="${OUTPUT_ROOT}/insights"
EXPERIMENTALIST_ROOT="${OUTPUT_ROOT}/experimentalist"
TRAIN_ROOT="${EXPERIMENTALIST_ROOT}/train"
VALIDATION_ROOT="${EXPERIMENTALIST_ROOT}/validation"
DATASET_REF="sierra-research/tau3-bench@1"

INSIGHTS_TASKS=(
  "tau3-bench__tau3-airline-0"
  "tau3-bench__tau3-airline-1"
  "tau3-bench__tau3-airline-4"
  "tau3-bench__tau3-airline-5"
  "tau3-bench__tau3-airline-9"
  "tau3-bench__tau3-airline-10"
  "tau3-bench__tau3-airline-12"
  "tau3-bench__tau3-airline-14"
  "tau3-bench__tau3-airline-17"
  "tau3-bench__tau3-airline-20"
  "tau3-bench__tau3-airline-23"
  "tau3-bench__tau3-airline-27"
  "tau3-bench__tau3-airline-33"
  "tau3-bench__tau3-airline-34"
  "tau3-bench__tau3-airline-38"
  "tau3-bench__tau3-airline-39"
  "tau3-bench__tau3-airline-41"
  "tau3-bench__tau3-airline-42"
  "tau3-bench__tau3-airline-46"
  "tau3-bench__tau3-airline-47"
)
EXPERIMENTALIST_TRAIN_TASKS=(
  "tau3-bench__tau3-airline-0"
  "tau3-bench__tau3-airline-4"
  "tau3-bench__tau3-airline-10"
  "tau3-bench__tau3-airline-20"
  "tau3-bench__tau3-airline-34"
  "tau3-bench__tau3-airline-39"
)
EXPERIMENTALIST_VALIDATION_TASKS=(
  "tau3-bench__tau3-airline-3"
  "tau3-bench__tau3-airline-12"
  "tau3-bench__tau3-airline-27"
  "tau3-bench__tau3-airline-36"
)

if [[ ! -f "${DATASET_ROOT}/${INSIGHTS_TASKS[0]}/task.toml" ]]; then
  mkdir -p "${SOURCE_ROOT}"
  (
    cd "${PLUGIN_ROOT}"
    uv run --frozen harbor download "${DATASET_REF}" \
      --output-dir "${SOURCE_ROOT}" \
      --export \
      --overwrite
  )
fi

validate_source() {
  local task_names=("$@")
  for task_name in "${task_names[@]}"; do
    if [[ ! -f "${DATASET_ROOT}/${task_name}/task.toml" ]]; then
      echo "Downloaded dataset is missing ${task_name}" >&2
      exit 1
    fi
  done
}

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
    cp -R "${source_task}" "${split_root}/${task_name}"
  done
}

validate_source \
  "${INSIGHTS_TASKS[@]}" \
  "${EXPERIMENTALIST_TRAIN_TASKS[@]}" \
  "${EXPERIMENTALIST_VALIDATION_TASKS[@]}"

prepare_split "${INSIGHTS_ROOT}" "${INSIGHTS_TASKS[@]}"
prepare_split "${TRAIN_ROOT}" "${EXPERIMENTALIST_TRAIN_TASKS[@]}"
prepare_split "${VALIDATION_ROOT}" "${EXPERIMENTALIST_VALIDATION_TASKS[@]}"

echo "Tau3 Airline datasets are ready:"
echo "  insights:                   ${INSIGHTS_ROOT}"
echo "  experimentalist train:      ${TRAIN_ROOT}"
echo "  experimentalist validation: ${VALIDATION_ROOT}"
