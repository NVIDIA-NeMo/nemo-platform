# CVE Summary

## Artifacts Reviewed

- `.cve-artifacts/29823504036/pulse-container-scan-auditor-tasks-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-api-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-automodel-training-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-cpu-tasks-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-customizer-tasks-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-rl-training-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-nmp-unsloth-training-29823504036.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-safe-synthesizer-tasks-29823504036-rerun.zip`
- `.cve-artifacts/29823504036/pulse-container-scan-safe-synthesizer-tasks-29823504036.zip`
- `.cve-artifacts/31002650434/pulse-oss-scan-31002650434.zip`
- Platform-Deploy OSS job: `https://github.com/NVIDIA-NeMo/Platform-Deploy/actions/runs/31002650434/job/92350606249`
- Branch context: `origin/remove-perl/rsadler` at `eb6c093a`, `cve-0723/mck` at `717d5e61f`, and `cve-0721/mck` at `27d057f45`.
- Relevant external context: PR `https://github.com/NVIDIA-NeMo/nemo-platform/pull/1056` addresses RL-base CVE and vLLM venv work, but is not merged into this branch.

No `dt_oss_*.csv` dependency CSV was present. Project dependency findings came from the Platform-Deploy Pulse OSS `security.yml` artifact. The non-rerun Safe Synthesizer ZIP did not contain `reports/vulns.json`; the rerun ZIP did.

## Input Counts

| Category | Critical | High | Total |
| --- | ---: | ---: | ---: |
| Project dependencies | 1 | 33 | 34 |
| Container-only | 84 | 429 | 513 |
| Total | 85 | 462 | 547 |

## Changes Made

- Raised root constraints from `GitPython>=3.1.49` to `GitPython>=3.1.57`; `uv.lock` now resolves `gitpython 3.1.58`.
- Added `datamodel-code-generator>=0.71.0` to root constraints and raised `services/core/models` dev dependency to `>=0.71.0`; `uv.lock` now resolves `datamodel-code-generator 0.72.1`.
- Raised root constraints and overrides from `pyasn1>=0.6.3` to `pyasn1>=0.6.4`; `uv.lock` now resolves `pyasn1 0.6.4`.
- Updated `docker/Dockerfile.auditor-tasks` direct CVE-remediation installs to require `pyasn1>=0.6.4`.
- Updated `services/guardrails/callouts` from `google.golang.org/grpc v1.81.1` to `v1.83.0`; `golang.org/x/net` remains fixed at `v0.56.0`.
- Updated Studio web test catalog and lockfile from `vitest 4.1.9` to `4.1.10`, including matching `@vitest/coverage-v8` and `@vitest/ui`.
- Added missing stale Pillow cleanup to `docker/automodel/Dockerfile.nmp-automodel-base`.
- Added `pillow>=12.3.0,<13` and stale system-site Pillow cleanup to `docker/Dockerfile.nmp-unsloth-training`.
- Added stale system-site Pillow cleanup to `docker/scripts/cve-cleanup.sh`.
- Reused `docker/scripts/cve-cleanup.sh` in `docker/Dockerfile.nmp-cpu-tasks` after the CPU task venv is copied, so the runtime image purges Perl packages without removing git from the builder stage.

## Findings Addressed

- OSS `golang/net v0.43.0` Critical row for `services/core/jobs/jobs-launcher` is addressed by the existing jobs-launcher module update to `golang.org/x/net v0.56.0`.
- OSS `grpc-go` rows for `services/core/jobs/jobs-launcher` and `services/guardrails/callouts` are addressed by `google.golang.org/grpc v1.83.0` in both Go modules.
- OSS `GitPython 3.1.50` rows are addressed by `GitPython>=3.1.57` and lock resolution to `3.1.58`.
- OSS `datamodel-code-generator 0.55.0` rows are addressed by `datamodel-code-generator>=0.71.0` and lock resolution to `0.72.1`.
- OSS `vitest 4.1.9` row is addressed by the Studio web catalog and lockfile resolving `vitest`, `@vitest/coverage-v8`, and `@vitest/ui` to `4.1.10`.
- `nmp-cpu-tasks` Perl package rows: 12 Critical and 16 High rows across `perl-base`, `perl`, `perl-modules-5.36`, and `libperl5.36` are addressed by the runtime cleanup step.
- `nmp-automodel-training` Pillow rows: 10 High rows for stale `/usr/local/lib/python3.12/dist-packages/pillow-12.2.0` copies are addressed by removing shadowed system-site Pillow.
- `nmp-unsloth-training` Pillow rows: 10 High rows for stale `/usr/local/lib/python3.12/dist-packages/pillow-12.2.0` copies are addressed by installing Pillow `>=12.3.0,<13` into `/opt/venv` and removing the shadowed system copy.
- `pyasn1` context from `cve-0723/mck`: root and Auditor direct install constraints now require `0.6.4`.
- Existing PR branch fixes retained: Safe Synthesizer and Auditor Perl cleanup, jobs-launcher Go module updates, Safe Synthesizer `pillow>=12.3.0`, and existing Customizer Pillow cleanup.
- Existing current lock state already resolves scan-stale project-controlled rows for `mcp 1.28.1`, `pyarrow 24.0.0`, `pillow 12.3.0`, and `wandb 0.28.1`.

## Findings Not Addressed

- OSS LangChain-family rows remain unresolved. The report groups `langchain-milvus 0.3.3`, `langchain-community 0.3.31`, `langchain-exa 1.1.0`, `langchain-huggingface 1.2.2`, and `langchain 1.3.14` under package name `langchain` with fixed guidance `0.4.0`. This is not directly applicable across those distributions, and the repo currently caps `langchain-community<0.4` because `0.4.x` removes the Vertex AI import path used by `ragas 0.4.3`. Addressing these needs a coordinated `ragas`/`nvidia-nat-langchain`/guardrails compatibility update or a scanner policy decision.
- OSS `ragas 0.4.3` High row remains unresolved because the Pulse OSS artifact reports `unknown` for both short-term and long-term upgrade guidance, and the repo currently pins `ragas==0.4.3` in SDK/evaluator extras.
- `nmp-api` Perl package rows remain unresolved. The API image includes the experimentalist plugin, whose runtime repository component shells out to `git`; purging Perl packages also removes `git`, so applying the cleanup there would be a behavior change without a replacement design.
- `nmp-api` and `nmp-cpu-tasks` scan rows tied to the old `/app/.venv/lib/python3.11` path need a fresh scan. Current source uses `python:3.13.14-slim-trixie` and the lock resolves fixed `mcp` and `pyarrow` versions.
- `nmp-rl-training` FFmpeg cache rows need a fresh scan against the current `docker/rl/` source-build layout. PR #1056 addresses several RL-base items, including Nsight removal, Python/uv/OpenSSL updates, Ray JAR cleanup, and vLLM venv handling, but those changes are not on this branch yet.
- `nmp-rl-training` W&B `wandb-core`, Go stdlib, Ray, SGLang, Transformers, and related RL-cache rows remain source-risk items until the RL base image and external NeMo-RL lock/cache are rebuilt and rescanned, or PR #1056 lands and is incorporated.
- Python binary rows with fixes such as `3.13.14` are expected to be stale for API/CPU because the current Dockerfiles already use `python:3.13.14-slim-trixie`; they still require image rebuild and rescan proof.
- OS package rows with no fixed version, such as some `libssh2` and Perl rows in `nmp-api`, remain unresolved or accepted pending upstream/base-image strategy.

## Overrides Or Constraints

- Added or raised compatible constraints:
  - `GitPython>=3.1.57`
  - `datamodel-code-generator>=0.71.0`
  - `pyasn1>=0.6.4`
- No new suppression, allowlist, or VEX decision was added.

## Verification

- `uv run python /home/mkornfield/home/skills/address-cves/scripts/summarize_findings.py --download-dir .cve-artifacts/31002650434 --force-download .cve-artifacts/29823504036 https://github.com/NVIDIA-NeMo/Platform-Deploy/actions/runs/31002650434/job/92350606249 --limit 0`: summarized 1 Critical and 33 High project dependency findings plus 84 Critical and 429 High container findings.
- `uv lock --upgrade-package GitPython --upgrade-package pyasn1 --upgrade-package datamodel-code-generator`: resolved successfully.
- `uv lock --check`: passed.
- `uv tree --frozen --package datamodel-code-generator --depth 1`: `datamodel-code-generator v0.72.1`.
- `uv tree --frozen --package gitpython --depth 1`: `gitpython v3.1.58`.
- `uv tree --frozen --package pyasn1 --depth 1`: `pyasn1 v0.6.4`.
- `uv tree --frozen --package pillow --depth 1`: `pillow v12.3.0`.
- `uv tree --frozen --package mcp --depth 1`: `mcp v1.28.1`.
- `uv tree --frozen --package pyarrow --depth 1`: `pyarrow v24.0.0`.
- `uv tree --frozen --package langchain-community --depth 1`: remains `langchain-community v0.3.31` under the documented `<0.4` compatibility cap.
- `uv tree --frozen --package ragas --depth 1`: remains `ragas v0.4.3` under the current SDK/evaluator pin.
- `cd services/core/jobs/jobs-launcher && go test ./... -v`: passed.
- `cd services/guardrails/callouts && go list -m all | rg 'google.golang.org/grpc|golang.org/x/net' && go test ./... -v`: `google.golang.org/grpc v1.83.0`, `golang.org/x/net v0.56.0`; tests passed.
- `cd web && pnpm install --lockfile-only`: passed and updated `web/pnpm-lock.yaml`; it warned that local Node `v22.18.0` is below the repo engine `>=22.23.2 <23`.
- `rg -n "vitest@4\.1\.9|@vitest/(coverage-v8|ui)@4\.1\.9|vitest: \^4\.1\.9|version: 4\.1\.9" web/pnpm-workspace.yaml web/pnpm-lock.yaml`: no stale `4.1.9` lock/catalog entries found.
- `git diff --check`: passed.
- `bash -n docker/scripts/cve-cleanup.sh`: passed.
- `docker buildx bake --print nmp-cpu-tasks-docker`: parsed bake definitions successfully.

Container images were not rebuilt or rescanned in this pass; a fresh Pulse scan is required to prove container rows disappear. Studio tests were not run because the local Node version is below the repo's required engine.
