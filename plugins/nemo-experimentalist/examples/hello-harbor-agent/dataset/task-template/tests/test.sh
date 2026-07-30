#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Harbor copies this directory to /tests in the task container and runs this
# script after the agent phase. Its only job is to write numeric rewards to
# /logs/verifier/reward.json — every value must be a plain number, and every
# task must emit the SAME keys, because the Experimentalist averages metrics
# across trials and rejects inconsistent metric sets.
#
# Emitted metrics:
#   reward     1.0 when the output line matches tests/expected.txt exactly
#   format_ok  1.0 when the agent wrote an output file at all
#
# Never `set -e` here: a non-zero exit before reward.json is written turns a
# legitimate 0 score into a missing metric.
set -uo pipefail

mkdir -p /logs/verifier

OUTPUT=/app/artifacts/output.txt
# Whole-file comparison, not just the first line: the agent under test is
# LLM-generated code the optimizer is actively reward-maximizing, so a verifier
# that ignores trailing output is a reward-hacking surface. Command substitution
# strips trailing newlines on both sides, so only trailing blank lines are
# tolerated — any extra content fails.
#
# CRLF pairs are normalized at end-of-line only. `tr -d '\r'` would delete
# *every* carriage return, so `sum=4<CR>2` would collapse to `sum=42` and score a
# false 1.0 — the same reward-hacking class as the trailing-output hole above.
EXPECTED_FILE=/tests/expected.txt
reward=0.0
format_ok=0.0

# Fail closed on a missing fixture. `set -e` is deliberately off (see above), so a
# failed read would otherwise leave EXPECTED empty and let an empty output compare
# equal to it and score 1.0.
if [ ! -r "$EXPECTED_FILE" ]; then
  echo "FAIL: ${EXPECTED_FILE} is missing or unreadable; refusing to score"
elif [ -f "$OUTPUT" ]; then
  EXPECTED="$(sed 's/\r$//' "$EXPECTED_FILE")"
  format_ok=1.0
  ACTUAL="$(sed 's/\r$//' "$OUTPUT")"
  echo "expected: [${EXPECTED}]"
  echo "actual:   [${ACTUAL}]"
  if [ "$ACTUAL" = "$EXPECTED" ]; then
    reward=1.0
  fi
else
  echo "FAIL: ${OUTPUT} was not created by the agent"
fi

printf '{"reward": %s, "format_ok": %s}\n' "$reward" "$format_ok" > /logs/verifier/reward.json
cat /logs/verifier/reward.json
