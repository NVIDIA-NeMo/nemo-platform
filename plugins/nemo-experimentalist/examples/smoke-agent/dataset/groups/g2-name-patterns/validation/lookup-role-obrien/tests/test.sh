#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Harbor copies this directory to /tests and runs this after the agent phase. Its
# only job is to write numeric rewards to /logs/verifier/reward.json.
#
#   reward     1.0 when the output matches tests/expected.txt exactly
#   shape_ok   1.0 when the first line has the `<key>=<value>` shape, whatever
#              the value. This is the discriminating second metric: it separates
#              answering the wrong question from not answering at all. Do not
#              replace it with a wrote-a-file check — the agent always writes
#              one, so that metric would be constant and the ranking 1-D.
#
# Never `set -e`: exiting before reward.json is written turns a legitimate 0 into
# a *missing* metric, which the Experimentalist treats very differently.
set -uo pipefail

mkdir -p /logs/verifier

OUTPUT=/app/artifacts/output.txt
EXPECTED_FILE=/tests/expected.txt
reward=0.0
shape_ok=0.0

# Fail closed. With `set -e` off, an unreadable fixture would otherwise leave the
# expectation empty, and empty compares equal to empty — a broken fixture would
# score 1.0.
if [ ! -r "$EXPECTED_FILE" ]; then
  echo "FAIL: ${EXPECTED_FILE} is missing or unreadable; refusing to score"
elif [ -f "$OUTPUT" ]; then
  # Shape check on the first line only: right form, value not considered. `grep -q`
  # is silent on purpose — echoing the line would put answers in the trial log,
  # which the Coder can read.
  if head -n 1 "$OUTPUT" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*='; then
    shape_ok=1.0
  fi
  # Byte-for-byte over the whole file. Command substitution would strip trailing
  # newlines on both sides, letting an agent append blank lines and still score.
  # CRLF is normalized at end-of-line only: `tr -d '\r'` would delete every CR,
  # so `sum=4<CR>2` would collapse into a passing `sum=42`.
  EXPECTED_NORM="$(mktemp)"
  ACTUAL_NORM="$(mktemp)"
  sed 's/\r$//' "$EXPECTED_FILE" > "$EXPECTED_NORM"
  sed 's/\r$//' "$OUTPUT" > "$ACTUAL_NORM"
  if cmp -s "$EXPECTED_NORM" "$ACTUAL_NORM"; then
    reward=1.0
  fi
  rm -f "$EXPECTED_NORM" "$ACTUAL_NORM"
else
  echo "FAIL: ${OUTPUT} was not created by the agent"
fi

printf '{"reward": %s, "shape_ok": %s}\n' "$reward" "$shape_ok" > /logs/verifier/reward.json
cat /logs/verifier/reward.json
