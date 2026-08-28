<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Anonymizer Examples

This spec is usable from the repo root. It points at the checked-in
`anonymizer-input.csv`; pass `--fileset` and the CLI uploads it before calling
the Anonymizer service.

```bash
nemo anonymizer preview \
  --spec-file plugins/nemo-anonymizer/examples/redact.yaml \
  --num-records 2 \
  --fileset anonymizer-inputs \
  --workspace "${NMP_WORKSPACE:-default}" \
  --output-file preview.ndjson

nemo anonymizer run \
  --spec-file plugins/nemo-anonymizer/examples/redact.yaml \
  --fileset anonymizer-inputs \
  --workspace "${NMP_WORKSPACE:-default}" \
  --watch \
  --output-dir ./anonymizer-artifacts
```
