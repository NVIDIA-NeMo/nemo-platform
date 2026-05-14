#!/usr/bin/env bash
set -euo pipefail
# Run corresponding lint-fix scripts in dependency order. Each entry in
# LINT_FIX_ORDER is a lint name and maps mechanically to lint-fix-<suffix>.sh.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lint-common.sh"
cd "${PROJECT_ROOT}" || exit 1

use_failed=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --failed)
      use_failed=true
      ;;
    -h|--help)
      echo "Usage: $0 [--failed]"
      echo ""
      echo "Environment:"
      echo "  LINTS=\"lint-openapi lint-python-style\"  Run fixes for a subset."
      echo "  LINT_FAILURES_FILE=.lint-failures        Override failed-lint state file."
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

validate_lint_fix_pairs || exit 1

declare -a lint_names=()
declare -a requested_lints=()
if [[ "${use_failed}" == "true" ]]; then
  if [[ -n "${LINTS:-}" ]]; then
    echo "Use either --failed or LINTS=..., not both." >&2
    exit 1
  fi

  failed_output="$(read_lint_failures)" || exit 1
  if [[ -z "${failed_output}" ]]; then
    echo "No recorded lint failures in $(lint_failure_file_display_path). Run 'make lint' first."
    exit 0
  fi

  mapfile -t requested_lints <<< "${failed_output}"
  ordered_output="$(ordered_fix_lint_names "${requested_lints[@]}")" || exit 1
  if [[ -n "${ordered_output}" ]]; then
    mapfile -t lint_names <<< "${ordered_output}"
  fi
  echo "Selected fixes from $(lint_failure_file_display_path): ${lint_names[*]}"
elif [[ -n "${LINTS:-}" ]]; then
  requested_output="$(normalize_lint_names_from_text "${LINTS}")" || exit 1
  if [[ -n "${requested_output}" ]]; then
    mapfile -t requested_lints <<< "${requested_output}"
  fi
  ordered_output="$(ordered_fix_lint_names "${requested_lints[@]}")" || exit 1
  if [[ -n "${ordered_output}" ]]; then
    mapfile -t lint_names <<< "${ordered_output}"
  fi
  echo "Selected fixes: ${lint_names[*]}"
else
  lint_names=("${LINT_FIX_ORDER[@]}")
fi

declare -a failed=()
declare -a timing_rows=()
for lint_name in "${lint_names[@]}"; do
  name="$(lint_fix_script_name "${lint_name}")"
  path="$(lint_fix_script_path "${lint_name}")"
  display_path="$(lint_fix_script_display_path "${lint_name}")"
  echo ">>> ${lint_name} -> ${display_path}"
  start=$(date +%s)
  if bash "${path}"; then
    echo "[DONE] ${name}"
    result="DONE"
  else
    echo "[FAIL] ${name}"
    failed+=("${name}")
    result="FAIL"
  fi
  elapsed=$(( $(date +%s) - start ))
  timing_rows+=("$(printf '%-40s %s' "${name}" "${result} ${elapsed}s")")
  echo ""
done

echo "--- Fix summary ---"
echo "Completed: $((${#lint_names[@]} - ${#failed[@]}))"
echo "Failed: ${#failed[@]}"
echo ""
echo "Timings:"
for row in "${timing_rows[@]}"; do
  printf '  %s\n' "${row}"
done
if [[ ${#failed[@]} -gt 0 ]]; then
  echo ""
  echo "Failed steps: ${failed[*]}"
  exit 1
fi
if [[ "${use_failed}" == "true" ]]; then
  echo ""
  echo "Run 'make lint' to verify and refresh $(lint_failure_file_display_path)."
fi
exit 0
