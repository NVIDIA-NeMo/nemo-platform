#!/usr/bin/env bash
set -uo pipefail
# Run all lint scripts serially, report summary, exit with failure if any failed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lint-common.sh"
cd "${PROJECT_ROOT}" || exit 1

validate_lint_fix_pairs || exit 1

selected_output="$(selected_lint_names "${LINT_SCRIPT_NAMES[@]}")" || exit 1
declare -a lint_names=()
if [[ -n "${selected_output}" ]]; then
  mapfile -t lint_names <<< "${selected_output}"
fi

if [[ ${#lint_names[@]} -eq 0 ]]; then
  echo "No lint scripts selected."
  write_lint_failures || exit 1
  exit 0
fi

if [[ -n "${LINTS:-}" ]]; then
  echo "Selected lints: ${lint_names[*]}"
fi

declare -a failed=()
declare -a timing_lines=()
for name in "${lint_names[@]}"; do
  path="$(lint_script_path "${name}")"
  start=$(date +%s)
  if bash "${path}"; then
    echo "[PASS] ${name}"
    result="PASS"
  else
    echo "[FAIL] ${name}"
    failed+=("${name}")
    result="FAIL"
  fi
  elapsed=$(( $(date +%s) - start ))
  timing_lines+=("${name}:${result} ${elapsed}s")
done

echo ""
echo "--- Lint summary ---"
echo "Passed: $((${#lint_names[@]} - ${#failed[@]}))"
echo "Failed: ${#failed[@]}"
echo ""
echo "Timings:"
for line in "${timing_lines[@]}"; do
  name="${line%%:*}"
  details="${line#*:}"
  printf "  %-40s %s\n" "${name}" "${details}"
done
if [[ ${#failed[@]} -gt 0 ]]; then
  write_lint_failures "${failed[@]}" || exit 1
  echo "Failed lints: ${failed[*]}"
  echo "Recorded failed lints in $(lint_failure_file_display_path)."
  echo ""
  echo "To run fixes for the recorded failures in dependency order:"
  echo "  make lint-fix-failed"
  echo ""
  echo "To run fixes for a specific subset:"
  echo "  make lint-fix LINTS=\"${failed[*]}\""
  echo ""
  echo "Failed lint -> corresponding fix script:"
  for name in "${failed[@]}"; do
    printf "  %-30s %s\n" "${name}" "$(lint_fix_script_display_path "${name}")"
  done
  exit 1
fi
write_lint_failures || exit 1
exit 0
