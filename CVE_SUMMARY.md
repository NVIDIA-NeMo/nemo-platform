# CVE Summary

Date: 2026-08-10

## Scan Artifacts Reviewed

- `/home/mkornfield/cve-remediation.csv`

## Scope

The CSV has 353 Critical/High rows. Per the ownership note, this pass reviewed the full file but focused remediation and VEX text on rows outside `nmp-automodel-training`; the 99 `nmp-automodel-training` High rows are left to the Automodel owners.

The bundled `address-cves` summarizer was run against the CSV, but it skipped the file because this spreadsheet uses a custom schema (`Branch,Service,Package,Version,Path,CVE,...`) rather than the supported `dt_oss_*` or Pulse artifact schemas. Counts below come from direct CSV parsing.

## Critical and High Counts Before This Pass

| Scope / category | Critical | High | Total |
| --- | ---: | ---: | ---: |
| Full CSV | 33 | 320 | 353 |
| Excluded `nmp-automodel-training` | 0 | 99 | 99 |
| Non-Automodel project/source rows | 1 | 33 | 34 |
| Non-Automodel container/image rows | 32 | 188 | 220 |
| Non-Automodel total | 33 | 221 | 254 |

## Changes Made

- `docker/Dockerfile.auditor-tasks`: raised direct `aiohttp` remediation installs from `>=3.13.3` to `>=3.14.3,<4` for both `/app/.venv` and `/app/.garak_venv`.
- `docker/Dockerfile.safe-synthesizer-tasks`: added `aiohttp>=3.14.3,<4` to the Safe Synthesizer runtime override set.
- `docker/Dockerfile.nmp-unsloth-training`: raised the `/opt/venv` `aiohttp` floor to `>=3.14.3,<4`.
- `docker/Dockerfile.nmp-unsloth-training`: added cleanup of stale NGC system `GitPython` and `jupyterlab` copies under `/usr/local/lib/python3.12/dist-packages`; the image already installs patched runtime deps in `/opt/venv`.
- `docker/Dockerfile.nmp-api`: changed the final runtime stage from the shared slim Python base to NVIDIA distroless Python `nvcr.io/nvidia/distroless/python:3.13-v4.0.9`, while keeping the builder on the existing slim Python base and preserving the previous root runtime UID for mounted storage compatibility.
- `docker-bake.hcl`: added `NMP_API_RUNTIME_BASE` so the API runtime base can be overridden without changing the build base.

## Findings Addressed

### Project/source rows

- `datamodel-code-generator 0.55.0` source rows are addressed by the existing root constraint `datamodel-code-generator>=0.71.0` and current `uv.lock` resolution.
- `GitPython 3.1.50` source rows are addressed by the existing root constraint `GitPython>=3.1.57` and current `uv.lock` resolution.
- `grpc-go` / `golang.org/x/net` source rows for `services/core/jobs/jobs-launcher` and `services/guardrails/callouts` are addressed in current `go.mod` files with `google.golang.org/grpc v1.83.0` and `golang.org/x/net v0.56.0`.
- `vitest 4.1.9` source row is addressed by current `web/pnpm-lock.yaml` entries resolving `vitest 4.1.10`.
- LangChain rows marked `false positive` are consistent with scanner package-name confusion around LangChain integration packages rather than the vulnerable `langchain` package.
- The `ragas 0.4.3` row remains `not_affected`: evaluator SDK lazy-loads supported text metrics and does not expose the vulnerable multimodal metric path.

### Container/image rows

- `auditor-tasks` `aiohttp` row is addressed by this pass with `aiohttp>=3.14.3,<4`.
- `auditor-tasks` `cryptography` rows were already addressed by `cryptography>=50.0.0,<51` in both auditor venv install paths.
- `auditor-tasks` Perl rows are addressed by the auditor base stage purging Perl packages from the final image.
- `safe-synthesizer-tasks` `aiohttp` row is addressed by this pass with `aiohttp>=3.14.3,<4`.
- `safe-synthesizer-tasks` `cryptography` row was already addressed by `cryptography>=50.0.0,<51`; W&B is already pinned to `wandb==0.28.1`.
- `safe-synthesizer-tasks` Perl rows are addressed by the shared `docker/scripts/cve-cleanup.sh` cleanup in the final image.
- `nmp-api` Perl and `libssh2` `pkgdb` rows are expected to be addressed by the API runtime switch to NVIDIA distroless Python 3.13, whose inspected base has Python 3.13.14 and does not contain `/bin/sh`, `/usr/bin/git`, `/usr/bin/perl`, or libssh2.
- `nmp-unsloth-training` `aiohttp`, stale system `GitPython`, and stale system `jupyterlab` rows are addressed by this pass.
- `nmp-unsloth-training` `pillow` rows were already addressed by installing `pillow>=12.3.0,<13` and removing stale system `PIL` / `pillow-*` copies.
- `nmp-unsloth-training` W&B stdlib/grpc rows should clear on rebuild where the existing `docker/unsloth/no_override_requirements.txt` pin `wandb==0.28.1` is applied; W&B is optional and skipped unless configured with credentials/settings.
- `nmp-rl-training` OpenSSL rows are already addressed in `docker/rl/Dockerfile.nmp-rl-base` by targeted `apt-get install --only-upgrade openssl libssl3t64`.
- `nmp-rl-training` Ray `jackson-core` / `jackson-databind` rows are already addressed by removing `ray/jars` from the uv cache before prefetched venvs are materialized.
- `nmp-rl-training` Nsight Go stdlib rows are already addressed by removing Nsight Systems / Nsight Compute from the published image.
- `nmp-rl-training` `vllm` rows are expected to clear from paths that were only stale inherited/cache copies after current image cleanup and rebuild.
- `nmp-rl-training` `quinn-proto` rows should clear from the uv binary after rebuilding with the current `UV_VERSION=0.11.33`.

## Findings Not Addressed Or Still Needing Owner Decision

- `nmp-automodel-training`: 99 High rows are intentionally not addressed here because they are owned by the Automodel remediation workstream.
- `nmp-api` distroless runtime: expected to clear the Perl/libssh2 rows, but still needs a successful image build, runtime smoke, and rescan before closure; the image intentionally preserves the previous root runtime UID until Docker/Kubernetes storage mounts are consistently writable by a non-root user.
- `nmp-rl-training` `mooncake/libetcd_wrapper.so`: eleven High rows for Go stdlib, `golang.org/x/net`, and `google.golang.org/grpc` are inside an external bundled binary under `/opt/uv_cache`; repo search found no NeMo Platform source references to `mooncake` or `libetcd_wrapper`, but fixing requires an upstream NeMo-RL/mooncake dependency bump or proving/removing the unused cached binary.
- Full remediation proof still requires rebuilding and rescanning affected images; static Dockerfile and bake parsing cannot prove final scanner disappearance.

## Suggested One-Sentence VEX / Justification Text

Use these as row-level text where a CVE cannot be fully addressed in this pass.

| Applies to | Suggested state | One-sentence justification |
| --- | --- | --- |
| `nmp-api` `libssh2-1t64` | `fixed_pending_rescan` | `The API final image now uses NVIDIA distroless Python 3.13, and inspection of that base found no libssh2 library; rebuild and rescan are needed to confirm the package is absent from the final image.` |
| `nmp-api` Perl packages | `fixed_pending_rescan` | `The API final image now uses NVIDIA distroless Python 3.13, and inspection of that base found no shell, git, or Perl executable; rebuild and rescan are needed to confirm the Perl packages are absent from the final image.` |
| `nmp-rl-training` `mooncake/libetcd_wrapper.so` | `under_investigation` | `The vulnerable Go modules are bundled inside an external mooncake binary in the uv cache with no NeMo Platform source references, so the fix is an upstream dependency bump or removal after confirming RL does not load that binary.` |
| CPython stdlib rows | `not_affected` | `Supported task and service paths do not call the vulnerable CPython APIs on attacker-controlled tar, streaming archive, HTML, XML, or reused decompressor inputs.` |
| `flash-attn` no-fix rows | `not_affected` | `Supported training paths use flash-attn kernels but do not call the vulnerable checkpoint-loading helper with attacker-controlled checkpoints.` |
| LangChain integration rows | `false_positive` | `The scanner matched LangChain integration package names rather than the vulnerable LangChain package, and the applicable LangSmith/LangChain packages in the current lock are at patched versions.` |
| W&B `wandb-core` Go rows | `not_affected` or `fixed_pending_rescan` | `W&B is optional and skipped without user configuration/credentials, and images with an explicit wandb==0.28.1 pin need rebuild/rescan evidence to confirm the bundled Go modules are patched.` |

## Overrides Or Constraints

- Existing root constraints already cover `GitPython>=3.1.57`, `aiohttp>=3.14.1` with current lock at `3.14.3`, `cryptography>=50.0.0,<51`, `datamodel-code-generator>=0.71.0`, `jupyterlab>=4.6.1`, `pillow>=12.3.0`, `pyasn1>=0.6.4`, and `wandb>=0.28.1`.
- This pass added direct Dockerfile constraints for `aiohttp>=3.14.3,<4` in Auditor, Safe Synthesizer, and Unsloth.
- This pass added `NMP_API_RUNTIME_BASE=nvcr.io/nvidia/distroless/python:3.13-v4.0.9` for the API final runtime.
- No new root `uv.lock` or `pyproject.toml` changes were needed.

## Verification

- `uv run python /home/mkornfield/.codex/skills/address-cves/scripts/summarize_findings.py /home/mkornfield/cve-remediation.csv` - ran; tool skipped the custom CSV schema, so manual parsing was used.
- Direct CSV parsing with Python - counted 353 total rows and 254 non-Automodel rows.
- `rg` source checks - found current fixed source versions for root Python constraints, `web/pnpm-lock.yaml`, `services/core/jobs/jobs-launcher/go.mod`, and `services/guardrails/callouts/go.mod`.
- `git diff --check` - passed.
- `docker buildx bake --print auditor-tasks-docker` - passed bake parse.
- `docker buildx bake --print nmp-api-docker` - passed bake parse and resolves `NMP_API_RUNTIME_BASE=nvcr.io/nvidia/distroless/python:3.13-v4.0.9`.
- `docker buildx bake --print safe-synthesizer-tasks-docker` - passed bake parse.
- `docker buildx bake --print nmp-unsloth-training` - passed bake parse.
- `docker run --rm --entrypoint python nvcr.io/nvidia/distroless/python:3.13-v4.0.9 ...` - confirmed Python 3.13.14, user `nvs`, writable `/tmp`, and absence of `/bin/sh`, `/usr/bin/git`, `/usr/bin/perl`, and libssh2.
- `docker run --rm --user 1000:1000 ... pathlib.Path("/data/files_storage").stat()` against a root-only mounted child directory - reproduced the CI `PermissionError`; the same check with `--user 0:0` passed.
- `BUILD_ARCH=linux/amd64 docker buildx bake --load nmp-api-docker` - attempted, but failed before reaching project layers because this environment cannot pull `ghcr.io/astral-sh/uv:0.9.14` (`failed to fetch oauth token: denied`); direct `docker pull ghcr.io/astral-sh/uv:0.9.14` fails with the same registry denial.

Not run: successful full image rebuilds and rescans, for example `docker buildx bake nmp-api-docker auditor-tasks-docker safe-synthesizer-tasks-docker nmp-unsloth-training` followed by the Pulse/container scan. Those are the required final verification steps for scanner closure.
