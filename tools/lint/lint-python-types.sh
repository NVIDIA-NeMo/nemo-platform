#!/usr/bin/env bash
set -euo pipefail
# Run Python type checker in CI.
#
# The rules below are globally suppressed for CI only because the existing
# codebase still contains pre-existing violations left over. 
# They should be fixed incrementally and re-enabled as they are fixed.
# Generate error reports by running `make reports` in script/ty_issues_report.
# Counts reflect the violation count at the time of suppression.
ci_ignored_rules=(
  invalid-argument-type   # 148
  unused-ignore-comment       # 14
  unused-type-ignore-comment  # triggered by SDK type changes
  unresolved-attribute    # 141
  not-subscriptable       # 19
  invalid-assignment      # 9
  invalid-return-type     # 11
  invalid-method-override # 4
  no-matching-overload    # 9
  unsupported-operator    # 6
)

ignore_args=()
for rule in "${ci_ignored_rules[@]}"; do
  ignore_args+=(--ignore "$rule")
done

uv run --frozen ty check "${ignore_args[@]}"
