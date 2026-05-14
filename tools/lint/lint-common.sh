#!/usr/bin/env bash

# Shared lint registry. Lint/fix pairing is mechanical:
#   tools/lint/lint-foo.sh -> tools/lint/lint-fix-foo.sh

LINT_TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${LINT_TOOLS_DIR}/../.." && pwd)}"
LINT_FAILURES_FILE="${LINT_FAILURES_FILE:-${PROJECT_ROOT}/.lint-failures}"

# Lints run by `make lint`, in reporting order.
declare -a LINT_SCRIPT_NAMES=(
  "lint-licenses"
  "lint-openapi"
  "lint-config-reference-docs"
  "lint-helm"
  "lint-python-style"
  "lint-python-types"
  "lint-python-sdk"
  "lint-sdk-vendored"
  "lint-web-sdk"
  "lint-cli"
  "lint-auth-config"
  "lint-merge-conflict"
  "lint-copyright-headers"
)

# Fixes run by `make lint-fix`, expressed as lint names so the script path is
# always the corresponding lint-fix script. The order is dependency-aware.
declare -a LINT_FIX_ORDER=(
  "lint-openapi"
  "lint-web-sdk"
  "lint-python-sdk"
  "lint-python-style"
  "lint-cli"
  "lint-sdk-vendored"
  "lint-licenses"
  "lint-auth-config"
  "lint-config-reference-docs"
  "lint-helm"
  "lint-copyright-headers"
  "lint-python-types"
  "lint-merge-conflict"
)

lint_script_name_from_file() {
  local file_name="$1"
  printf '%s\n' "${file_name%.sh}"
}

lint_script_path() {
  local lint_name="$1"
  printf '%s/%s.sh\n' "${LINT_TOOLS_DIR}" "${lint_name}"
}

lint_script_display_path() {
  local lint_name="$1"
  printf 'tools/lint/%s.sh\n' "${lint_name}"
}

lint_failure_file_display_path() {
  printf '%s\n' "${LINT_FAILURES_FILE#${PROJECT_ROOT}/}"
}

lint_fix_script_name() {
  local lint_name="$1"
  printf 'lint-fix-%s\n' "${lint_name#lint-}"
}

lint_fix_script_path() {
  local lint_name="$1"
  lint_script_path "$(lint_fix_script_name "${lint_name}")"
}

lint_fix_script_display_path() {
  local lint_name="$1"
  lint_script_display_path "$(lint_fix_script_name "${lint_name}")"
}

is_runnable_lint_name() {
  local lint_name="$1"
  case "${lint_name}" in
    lint-all|lint-common|lint-fix|lint-fix-*)
      return 1
      ;;
  esac
  [[ -f "$(lint_script_path "${lint_name}")" ]]
}

normalize_lint_name() {
  local raw_name="$1"
  local lint_name
  raw_name="${raw_name#./}"
  raw_name="${raw_name#tools/lint/}"
  raw_name="${raw_name%.sh}"

  case "${raw_name}" in
    lint-fix-*)
      lint_name="lint-${raw_name#lint-fix-}"
      ;;
    lint-*)
      lint_name="${raw_name}"
      ;;
    *)
      lint_name="lint-${raw_name}"
      ;;
  esac

  if ! is_runnable_lint_name "${lint_name}"; then
    echo "Unknown lint '${raw_name}'. Expected a tools/lint/lint-*.sh script name." >&2
    return 1
  fi

  printf '%s\n' "${lint_name}"
}

normalize_lint_names_from_text() {
  local raw_lints="$1"
  local raw_name
  local lint_name
  local seen=" "

  raw_lints="${raw_lints//,/ }"
  for raw_name in ${raw_lints}; do
    lint_name="$(normalize_lint_name "${raw_name}")" || return 1
    case "${seen}" in
      *" ${lint_name} "*)
        continue
        ;;
    esac
    seen+="${lint_name} "
    printf '%s\n' "${lint_name}"
  done
}

selected_lint_names() {
  if [[ -n "${LINTS:-}" ]]; then
    normalize_lint_names_from_text "${LINTS}"
    return
  fi

  printf '%s\n' "$@"
}

lint_name_in_list() {
  local needle="$1"
  shift
  local lint_name
  for lint_name in "$@"; do
    if [[ "${lint_name}" == "${needle}" ]]; then
      return 0
    fi
  done
  return 1
}

ordered_fix_lint_names() {
  local -a requested_lints=("$@")
  local lint_name

  for lint_name in "${LINT_FIX_ORDER[@]}"; do
    if lint_name_in_list "${lint_name}" "${requested_lints[@]}"; then
      printf '%s\n' "${lint_name}"
    fi
  done

  for lint_name in "${requested_lints[@]}"; do
    if ! lint_name_in_list "${lint_name}" "${LINT_FIX_ORDER[@]}"; then
      printf '%s\n' "${lint_name}"
    fi
  done
}

write_lint_failures() {
  if [[ $# -eq 0 ]]; then
    rm -f "${LINT_FAILURES_FILE}"
    return
  fi

  printf '%s\n' "$@" > "${LINT_FAILURES_FILE}"
}

read_lint_failures() {
  local raw_lints
  if [[ ! -s "${LINT_FAILURES_FILE}" ]]; then
    return 0
  fi

  raw_lints="$(tr '\n' ' ' < "${LINT_FAILURES_FILE}")"
  normalize_lint_names_from_text "${raw_lints}"
}

all_lint_script_names() {
  local path
  local file_name
  for path in "${LINT_TOOLS_DIR}"/lint-*.sh; do
    [[ -f "${path}" ]] || continue
    file_name="$(basename "${path}")"
    case "${file_name}" in
      lint-all.sh|lint-common.sh|lint-fix.sh|lint-fix-*.sh)
        continue
        ;;
    esac
    lint_script_name_from_file "${file_name}"
  done | sort
}

validate_lint_fix_pairs() {
  local lint_name
  local lint_path
  local fix_path
  local file_name
  local path
  local ordered_lint_name
  local found
  local -a missing_lints=()
  local -a missing_fixes=()
  local -a unregistered_lints=()
  local -a missing_fix_order=()
  local -a orphan_fixes=()

  for lint_name in "${LINT_SCRIPT_NAMES[@]}" "${LINT_FIX_ORDER[@]}"; do
    lint_path="$(lint_script_path "${lint_name}")"
    if [[ ! -f "${lint_path}" ]]; then
      missing_lints+=("$(lint_script_display_path "${lint_name}")")
    fi
  done

  while IFS= read -r lint_name; do
    [[ -n "${lint_name}" ]] || continue
    fix_path="$(lint_fix_script_path "${lint_name}")"
    if [[ ! -f "${fix_path}" ]]; then
      missing_fixes+=("$(lint_script_display_path "${lint_name}") -> $(lint_fix_script_display_path "${lint_name}")")
    fi
    if ! lint_name_in_list "${lint_name}" "${LINT_SCRIPT_NAMES[@]}"; then
      unregistered_lints+=("$(lint_script_display_path "${lint_name}")")
    fi
  done < <(all_lint_script_names)

  for lint_name in "${LINT_SCRIPT_NAMES[@]}"; do
    found=false
    for ordered_lint_name in "${LINT_FIX_ORDER[@]}"; do
      if [[ "${lint_name}" == "${ordered_lint_name}" ]]; then
        found=true
        break
      fi
    done
    if [[ "${found}" == "false" ]]; then
      missing_fix_order+=("${lint_name} -> $(lint_fix_script_display_path "${lint_name}")")
    fi
  done

  for path in "${LINT_TOOLS_DIR}"/lint-fix-*.sh; do
    [[ -f "${path}" ]] || continue
    file_name="$(basename "${path}")"
    lint_name="lint-${file_name#lint-fix-}"
    lint_name="${lint_name%.sh}"
    lint_path="$(lint_script_path "${lint_name}")"
    if [[ ! -f "${lint_path}" ]]; then
      orphan_fixes+=("$(lint_script_display_path "${lint_name}") <- tools/lint/${file_name}")
    fi
  done

  if [[ ${#missing_lints[@]} -gt 0 || ${#missing_fixes[@]} -gt 0 || ${#unregistered_lints[@]} -gt 0 || ${#missing_fix_order[@]} -gt 0 || ${#orphan_fixes[@]} -gt 0 ]]; then
    if [[ ${#missing_lints[@]} -gt 0 ]]; then
      echo "Missing lint scripts referenced by tools/lint/lint-common.sh:"
      printf '  %s\n' "${missing_lints[@]}"
    fi
    if [[ ${#missing_fixes[@]} -gt 0 ]]; then
      echo "Missing corresponding lint-fix scripts:"
      printf '  %s\n' "${missing_fixes[@]}"
    fi
    if [[ ${#unregistered_lints[@]} -gt 0 ]]; then
      echo "Lint scripts missing from LINT_SCRIPT_NAMES:"
      printf '  %s\n' "${unregistered_lints[@]}"
    fi
    if [[ ${#missing_fix_order[@]} -gt 0 ]]; then
      echo "Lints run by make lint but missing from LINT_FIX_ORDER:"
      printf '  %s\n' "${missing_fix_order[@]}"
    fi
    if [[ ${#orphan_fixes[@]} -gt 0 ]]; then
      echo "Lint-fix scripts without corresponding lint scripts:"
      printf '  %s\n' "${orphan_fixes[@]}"
    fi
    return 1
  fi
}
