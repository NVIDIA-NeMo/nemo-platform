# Releasing NeMo Platform

This document describes the end-to-end process for cutting and shipping a new version of NeMo Platform.

> **Who can release?** Any team member can open the version bump PR and trigger the workflow. The `release-stable` GitHub Actions environment requires approval from a member of the `nmp_devops` team before the workflow proceeds.

---

## Overview

> The examples in this document use `0.1.2` as the version being released and `0.1.3` as the next development version.

```
merge version bump PR (0.1.3) → trigger release-stable.yaml at parent commit (0.1.2) → nmp_devops approval → Platform-Deploy publishes to PyPI
```

Artifacts published on a stable release:
- `nemo-platform` on [pypi.org](https://pypi.org/project/nemo-platform/)
- `nemo-platform-plugin` on [pypi.org](https://pypi.org/project/nemo-platform-plugin/)

Nightly builds go to `pypi.nvidia.com` (NVIDIA's internal/public PyPI mirror), **not** public PyPI.

---

## Step 1 — Merge the version bump PR first

Before triggering the release, merge a PR that bumps `version.py` to the *next* version (e.g. `0.1.2` → `0.1.3`). You will then release from the commit *just before* that merge — the last commit where `version.py` still reads `0.1.2`. This means:
- The bump is already on `main` before you touch the release workflow — no race window.
- Nightlies built after the bump PR merges will immediately produce `0.1.3.dev...` strings.

The bump PR must also regenerate the OpenAPI spec and SDKs, since they embed the version:

```bash
make update-sdk
```

This runs `make refresh-openapi` (regenerates `openapi/openapi.yaml` and plugin specs) and then syncs the Python and web SDKs via Stainless. Requires `STAINLESS_API_KEY` to be set — see `sdk/README.md` for setup instructions.

To find the right SHA:

```bash
git log --oneline main | head -5
# The second line is the commit just before the bump PR
```

Or find it in the GitHub commit history — it's the parent of the bump PR's merge commit.

---

## Step 2 — Trigger the stable release workflow

Navigate to the [`release-stable.yaml` workflow](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/release-stable.yaml) and click **Run workflow**.

| Input | Required | Description |
|---|---|---|
| `source_sha` | Yes | The full 40-character commit SHA to release from (must be on `main`). |
| `version` | Yes | SemVer core version string to release, e.g. `0.1.2`. Must match the value in `version.py` at `source_sha` (not the current `main`, which has already been bumped to `0.1.3`). |
| `release_date` | No | `YYYY-MM-DD`. Provide only on the first run for a given version; leave blank on reruns. |
| `release_scope` | No | `sdks` (default) — releases both `nemo-platform` and `nemo-platform-plugin`. Use `custom` + `sdk_ids` to release a subset. |

The workflow runs from the **`main` branch** by default. The `source_sha` must be reachable from that branch.

**What the workflow does:**
1. Validates inputs and previews the release.
2. Pauses at the `approve-stable-release` gate — a member of the **`nmp_devops` team** must approve in the GitHub environment UI.
3. Creates and pushes a git tag (e.g. `0.1.2`) at `source_sha`.
4. Builds Python wheels for each SDK in `release/assets.yaml` using `.github/actions/build-nemo-platform-wheel`.
5. Assembles a release bundle with checksums and metadata.
6. Dispatches a `release-bundle-produced` event to the **Platform-Deploy** repository (`CI_DISPATCH_REPO` secret), which handles the actual Kitmaker/PyPI publish.

> If Kitmaker is returning 5xx errors, the publish step in Platform-Deploy will fail. Wait for Kitmaker to recover and re-run the workflow with the same `source_sha` and `version` — the stable tag is already reserved so re-running is safe.

---

## Step 3 — Verification

Once the workflow completes, verify the release landed correctly:

```bash
uv tool upgrade nemo-platform
nemo --version
# Expected: nemo version <version>
```

Also check:
- [pypi.org/project/nemo-platform](https://pypi.org/project/nemo-platform/) — version and description updated.
- [pypi.org/project/nemo-platform-plugin](https://pypi.org/project/nemo-platform-plugin/) — version updated.
- GitHub: a tag (e.g. `0.1.2`) exists on the release commit.

---

## Nightly builds

Nightly builds run automatically at 20:00 PT and publish to `pypi.nvidia.com`. They use the HEAD of `main` and version strings like `0.1.3.dev20260101120000`. No action required from the team.

To trigger a nightly manually: [`release-nightly.yaml`](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/release-nightly.yaml) → **Run workflow** (no inputs required).

