<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CVE Remediation Summary

## Scan Artifacts Reviewed

- https://github.com/NVIDIA-NeMo/Platform-Deploy/actions/runs/33867119651/job/101004384369
  - `/tmp/nemo-address-cves-20260904/pulse-oss-scan-33867119651.zip`
- https://github.com/NVIDIA-NeMo/Platform-Deploy/actions/runs/33862649918
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-api-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-cpu-tasks-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-gym-tasks-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-auditor-tasks-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-safe-synthesizer-tasks-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-customizer-tasks-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-automodel-training-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-rl-training-33862649918.zip`
  - `/tmp/nemo-address-cves-20260904/pulse-container-scan-nmp-unsloth-training-33862649918.zip`

The container artifacts scanned image tag `580978986bc500a3d1aa5d72972f76c551f84d7b`.
This worktree is newer at `1fa27f98ef048392165c6fc8c442868017de57ce`, so some
container rows are stale relative to current source and need a rebuild/rescan to confirm.

## Counts Before Remediation

| Category | Critical | High | Total |
| --- | ---: | ---: | ---: |
| Project dependencies | 1 | 5 | 6 |
| Container-only | 21 | 137 | 158 |

## Changes Made

- Raised the root `GitPython` constraint from `>=3.1.58` to `>=3.1.60`; `uv.lock`
  now resolves `gitpython` to `3.1.61`.
- Raised container install floors for `GitPython` to `>=3.1.60,<4` in the Automodel,
  Customizer, and Unsloth task image Dockerfiles.
- Raised the root `typecheck` `transformers` range from `>=5.5.0,<5.9.0` to
  `>=5.16.1,<5.17.0`; `uv.lock` now resolves `transformers` to `5.16.1` and
  `tokenizers` to `0.23.2`.
- Added a pnpm override for vulnerable `nanoid` 5.x:
  `nanoid@>=5.0.0 <6.0.1 -> ^6.0.1`. `web/pnpm-lock.yaml` no longer contains
  `nanoid@5.1.9`.

## Findings Addressed

- `CVE-2026-79675` / `EUVD-2026-65525` and `CVE-2026-78680` / `EUVD-2026-65226`
  for `nltk 3.10.2`: already addressed in the current worktree before this pass by
  `nltk>=3.10.3` and lock resolution to `3.10.3`.
- `BDSA-2026-30097` / `CVE-2026-78676` and `BDSA-2026-30098` / `CVE-2026-78677`
  for `GitPython 3.1.58`: addressed by the root constraint, lock update to `3.1.61`,
  and matching container install floors.
- `BDSA-2026-31382` / `CVE-2026-73086` for `nanoid 5.1.9`: addressed by the pnpm
  override and lock update to `nanoid 6.0.1` for the affected `@assistant-ui` paths.
- `BDSA-2026-25434` / `CVE-2026-9856` for root `transformers 5.5.0`: addressed by
  the `typecheck` group update and lock resolution to `transformers 5.16.1`.

## Findings Not Addressed

- Container image rows from scanned tag `580978986bc500a3d1aa5d72972f76c551f84d7b`
  for Python `3.13.14`, Debian `libssl3t64`, and `openssl-provider-fips` are stale
  relative to current source: the current Python base is `python:3.13.15-slim-trixie`
  and the relevant Dockerfiles already run targeted apt upgrades for OpenSSL packages.
  A rebuild and new Pulse scan are needed to close these rows.
- `zlib1g 1:1.3.dfsg+really1.3.1-1+b1` container rows have no fixed version in the
  scan report.
- `flash-attn` container rows in Automodel, RL, and Unsloth training images have no
  fixed version in the scan report.
- `mlflow` and `wandb-core` container rows are emitted from training-image environments
  or cache materialization. Current source already pins `mlflow-skinny>=3.15.0,<3.16.0`
  and `wandb>=0.29.0`; rows without a fixed version, or rows from older built image
  caches, need upstream releases or a rebuild/rescan.
- `transformers` container rows remain for Automodel, RL, and Unsloth training image
  stacks. The Customizer task image already has `TRANSFORMERS_VERSION=5.10.4`, which
  addresses the scanned `GHSA-xrqw-3rrv-vx5w` row for that image. The remaining
  training stacks need stack-specific compatibility validation before forcing newer
  `transformers` inside those images.
- `thrift 0.20.0` was reported only from the older Automodel training image
  environment. It is not reproducible in current tracked manifests; current Automodel
  image source removes full `mlflow` and installs `mlflow-skinny`, so this needs a
  rebuild/rescan to confirm.

## Overrides And Constraints

- Added pnpm override `nanoid@>=5.0.0 <6.0.1: ^6.0.1` because the vulnerable
  `nanoid 5.1.9` is transitive through `@assistant-ui/react@0.12.28`, not a direct
  `package.json` dependency.
- Updated root uv constraints for `GitPython>=3.1.60` and the root `typecheck`
  dependency group for `transformers>=5.16.1,<5.17.0`.

## Verification

- `uv run python /home/mkornfield/home/skills/address-cves/scripts/summarize_findings.py --download-dir /tmp/nemo-address-cves-20260904 --force-download --limit 0 <scan URLs>`: downloaded and summarized 10 Pulse artifacts.
- `uv lock --check`: passed.
- `uv tree --frozen --package gitpython`: resolved `gitpython v3.1.61`.
- `uv tree --frozen --package transformers`: resolved `transformers v5.16.1` and `tokenizers v0.23.2`.
- `uv run --frozen --group typecheck python -c "import git, transformers, tokenizers; ..."`:
  imported the changed packages and printed `3.1.61`, `5.16.1`, and `0.23.2`.
- `pnpm install --lockfile-only`: passed; existing Node engine/peer warnings only.
- `pnpm install --lockfile-only --frozen-lockfile`: passed; existing Node engine warning only.
- `pnpm install`: passed; existing Node engine warning and ignored-build-script notices only.
- `pnpm -r why nanoid`: affected `@assistant-ui` and `assistant-stream` paths resolve to
  `nanoid 6.0.1`; the remaining `nanoid 3.3.17` path is through PostCSS/Vite.
- `pnpm --filter @nemo/common typecheck`: passed; existing Node engine warning only.
- `pnpm --filter nemo-studio-ui typecheck`: passed; existing Node engine warning only.
- Targeted old-version search in `uv.lock`, `web/pnpm-lock.yaml`, `pyproject.toml`, and
  `web/pnpm-workspace.yaml`: no matches for `gitpython 3.1.58`, `transformers 5.5.0`,
  `nanoid 5.1.9`, or `nltk 3.10.2`.
- `uv run --frozen ty check`: failed with 702 diagnostics already present across the branch;
  the first failures are in `agents/nemo-studio-assistant` tests and SDK typed-dict usage,
  not in this CVE dependency change.
