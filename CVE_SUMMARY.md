<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CVE Remediation Summary

Source scan:

- https://github.com/NVIDIA-NeMo/Platform-Deploy/actions/runs/33623270102

The `address-cves` summary for this run reported no Critical or High project dependency findings.
It reported 21 Critical and 111 High container-only findings across the downloaded
`pulse-container-scan-*` artifacts.

## Addressed

- Raised the root `nltk` constraint from 3.10.0 to 3.10.3, and the lock entry from 3.10.2
  to 3.10.3. This addresses the `nltk` findings reported in `nmp-api`, `nmp-cpu-tasks`,
  and `nmp-gym-tasks`.
- Raised the `nltk` post-install remediation floor in `docker/Dockerfile.auditor-tasks` to keep
  the auditor task image aligned with the fixed floor.
- Raised the explicit `nmp-customizer-tasks` `TRANSFORMERS_VERSION` Docker arg from 5.8.1 to
  non-yanked 5.10.4. This addresses the `transformers` finding reported for that image.

## Remaining Follow-Up

- `transformers` remains reported in `nmp-unsloth-training`, `nmp-rl-training`, and
  `nmp-automodel-training`. The root lock remains constrained by the current `unsloth` stack,
  and the Automodel/RL training images need stack-specific compatibility validation before forcing
  `transformers>=5.10.0`.
- `mlflow`, `thrift`, and `flash-attn` findings are emitted from training-image environments or
  cache materialization rather than the root project dependency set. `flash-attn` reported no fixed
  version in this scan.
- Debian `libssl3t64` and `openssl-provider-fips` rows reported a fix at `3.5.7-1~deb13u2`.
  The relevant Dockerfiles already perform apt upgrades, so this likely requires a rebuild with
  updated base repositories or base-image changes.
- Python `3.13.14` rows are stale relative to the current `release/0.5` branch, whose Python base
  image args are already `python:3.13.15-slim-trixie`.
