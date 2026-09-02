<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CVE Remediation Summary

Branch: `cve-release-0.5-2026-09-02/mkornfield`
Base: `origin/release/0.5` at `7b82e1ad8f0e506e1571ff534319c7e595739b98`
Date: 2026-09-02

## Artifacts Reviewed

- User-provided inline dependency finding list for `release/0.5` / `0.5.0`, scanned on 2026-09-01.
- No local `dt_oss_*.csv`, `pulse-oss-scan-*`, `pulse-container-scan-*`, or `oss-scan-report.json` artifacts were present in this worktree.
- External package metadata checked:
  - `https://pypi.org/project/ragas/`
  - `https://pypi.org/pypi/langchain-community/0.4.2/json`
  - `https://pypi.org/pypi/transformers/5.9.0/json`
  - `https://pypi.org/pypi/unsloth/json`
  - `https://pypi.org/pypi/unsloth-zoo/json`
  - `https://pypi.org/project/Pillow/`
  - `https://pypi.org/project/Pygments/`
  - `npm view browserslist version dist-tags --json`
  - `go list -m -versions google.golang.org/grpc`

## Finding Counts

- Critical project dependency findings reviewed: 0
- High project dependency findings reviewed: 12
- Container-only findings reviewed: 0

## Changes Made

- Tightened Fern documentation helper requirements:
  - `Pillow>=11.0.0` -> `Pillow>=12.3.0`
  - `Pygments>=2.18.0` -> `Pygments>=2.20.0`
- Added a web workspace override for vulnerable Browserslist ranges:
  - `browserslist@<4.28.7` -> `^4.28.8`
- Regenerated `web/pnpm-lock.yaml`; the resolved Browserslist chain is now:
  - `browserslist@4.28.8`
  - `update-browserslist-db@1.3.2`
  - `baseline-browser-mapping@2.11.20`
  - `caniuse-lite@1.0.30001810`
  - `electron-to-chromium@1.5.420`
  - `node-releases@2.0.54`
- Updated Guardrails callouts Go dependencies:
  - `google.golang.org/grpc v1.83.0` -> `v1.83.2`
  - `golang.org/x/net v0.56.0` -> `v0.58.0`
  - `golang.org/x/sys v0.46.0` -> `v0.47.0`
  - `golang.org/x/text v0.38.0` -> `v0.41.0`

## Addressed Findings

- `PillowPython 11.0.0`
  - Covered rows: `BDSA-2026-9047 / CVE-2026-42311`, `BDSA-2026-22406 / CVE-2026-59197`, `BDSA-2026-22384 / CVE-2026-54058`, `BDSA-2026-1883 / CVE-2026-25990`
  - Status: Addressed for repo-visible lower bounds. Root `uv.lock` was already at `pillow==12.3.0`; docs tooling now also requires `Pillow>=12.3.0`.
- `Pygments 2.18.0`
  - Covered row: `BDSA-2026-5113 / CVE-2026-4539`
  - Status: Addressed for repo-visible lower bounds. Root `uv.lock` was already at `pygments==2.20.0`; docs tooling now also requires `Pygments>=2.20.0`.
- `browserslist 4.28.4`
  - Covered row: `BDSA-2026-26977 / CVE-2026-73088`
  - Status: Addressed. `web/pnpm-lock.yaml` now resolves `browserslist@4.28.8`.
- `grpc-go v1.83.0-dev`
  - Covered row: `BDSA-2026-24094`
  - Status: Addressed in `services/guardrails/callouts`; `google.golang.org/grpc` now resolves to `v1.83.2`.

## Unresolved / Upstream-Blocked Findings

- `ragas 0.4.3`
  - Covered row: `CVE-2026-6587`
  - Status: Not upgraded. PyPI's latest `ragas` release is still `0.4.3`, so there is no upstream fixed release available to consume.
  - Rationale: `ragas` is a direct dependency of the evaluator SDK RAGAS metrics. Removing it from release/0.5 would be a breaking feature change, so this branch preserves functionality and documents the unresolved finding.
- `langchain-community 0.3.31` reported as `langchain 0.3.31`
  - Covered rows: `BDSA-2026-9844 / CVE-2026-44843`, `BDSA-2025-77504 / CVE-2025-68664`, `BDSA-2025-29575 / CVE-2025-65106`
  - Status: Not upgraded.
  - Rationale: `langchain` and `langchain-core` in the root lock are already newer (`langchain==1.3.17`, `langchain-core==1.6.0`), but `ragas==0.4.3` requires the old `langchain-community` import surface. A test install with `ragas==0.4.3` and `langchain-community>=0.4.2,<0.5` fails on import with `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`.
- `transformers 5.5.0`
  - Covered row: `BDSA-2026-25434 / CVE-2026-9856`
  - Status: Not upgraded in the shared Python lock or Unsloth training image.
  - Rationale: Current PyPI metadata shows latest `unsloth==2026.8.22`, latest `unsloth-zoo==2026.8.17`, and latest `transformers==5.16.1`. Every available `unsloth>=2026.8.4` release still caps `transformers` at `<=5.5.0`, so current-or-newer Unsloth cannot pair with a patched Transformers release. An unconstrained solve can pair `transformers>=5.9.0,<6.0` only by downgrading to `unsloth==2025.9.5`, which is not an upgrade path from release/0.5. The Docker training image also intentionally pins `transformers==5.5.0` for Unsloth compatibility.

## Verification

- `uv lock --check`
  - Passed.
- `flox -q activate -- uv run pre-commit run -a`
  - Passed.
- `make docs-check`
  - Passed after installing Fern docs dependencies with `make docs-deps`.
- `make docs-broken-links`
  - Completed but reported 10 pre-existing broken links in unrelated documentation pages for `opensandbox` and `/documentation/studio/plugins`.
- `pnpm install --lockfile-only` from `web/`
  - Passed and updated `web/pnpm-lock.yaml`.
  - Warning only: current Node `v22.18.0` is below the repo engine requirement `>=22.23.2 <23`.
- `pnpm install --frozen-lockfile` from `web/`
  - Passed; lockfile was up to date.
  - Warning only: current Node `v22.18.0` is below the repo engine requirement `>=22.23.2 <23`.
- `pnpm --filter="...[origin/release/0.5]" run --parallel --if-present typecheck` from `web/`
  - Passed; no package scripts emitted output for this dependency-only diff.
- `pnpm --filter="...[origin/release/0.5]" run --parallel --if-present test:ci` from `web/`
  - Passed; no package scripts emitted output for this dependency-only diff.
- `pnpm lint` from `web/`
  - Passed.
- `pnpm format` from `web/`
  - Passed.
- `pnpm deps:studio` from `web/`
  - Passed.
- `go test ./...` from `services/guardrails/callouts/`
  - Passed.
- `uv pip compile` isolated check for `unsloth==2026.8.4` with `transformers>=5.9.0,<6.0`
  - Failed as expected; resolver reports Unsloth requires a Transformers range ending at `<=5.5.0`.
- `uv pip compile` isolated check for `unsloth>=2026.8.4` with `transformers>=5.9.0,<6.0`
  - Failed as expected; resolver reports all current-or-newer Unsloth releases require a Transformers range ending at `<=5.5.0`.
- `uv pip compile` isolated check for `unsloth>=2026.8.4`
  - Resolved `unsloth==2026.8.22`, `unsloth-zoo==2026.8.17`, and `transformers==5.5.0`.
- `uv pip compile` isolated check for unconstrained `unsloth` with `transformers>=5.9.0,<6.0`
  - Resolved only by selecting older `unsloth==2025.9.5` with `transformers==5.16.1`.
- `uv run --no-project` isolated import check for `ragas==0.4.3` with `langchain-community>=0.4.2,<0.5`
  - Failed as expected with missing `langchain_community.chat_models.vertexai`.
