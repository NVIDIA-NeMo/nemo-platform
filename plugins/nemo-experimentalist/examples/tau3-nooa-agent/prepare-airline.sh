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
VALIDATION_TASKS=(
  "tau3-bench__tau3-airline-3"
  "tau3-bench__tau3-airline-7"
  "tau3-bench__tau3-airline-11"
  "tau3-bench__tau3-airline-15"
  "tau3-bench__tau3-airline-21"
  "tau3-bench__tau3-airline-28"
  "tau3-bench__tau3-airline-36"
  "tau3-bench__tau3-airline-40"
  "tau3-bench__tau3-airline-43"
  "tau3-bench__tau3-airline-49"
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

  mkdir -p "${split_root}"
  local existing_task_path existing_task_name expected
  for existing_task_path in "${split_root}"/*/task.toml; do
    existing_task_name="$(basename -- "$(dirname -- "${existing_task_path}")")"
    expected=false
    for task_name in "${task_names[@]}"; do
      if [[ "${existing_task_name}" == "${task_name}" ]]; then
        expected=true
        break
      fi
    done
    if [[ "${expected}" != true ]]; then
      echo "Existing split contains unexpected task ${existing_task_name}: ${split_root}" >&2
      exit 1
    fi
  done

  for task_name in "${task_names[@]}"; do
    if [[ -f "${split_root}/${task_name}/task.toml" ]]; then
      continue
    fi
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

echo "Tau3 Airline quality datasets are ready:"
echo "  train:      ${TRAIN_ROOT} (${#TRAIN_TASKS[@]} tasks)"
echo "  validation: ${VALIDATION_ROOT} (${#VALIDATION_TASKS[@]} tasks)"
