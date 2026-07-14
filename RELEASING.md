# Releasing NeMo Platform

This document describes the end-to-end process for cutting and shipping a new version of NeMo Platform.

> **Who can release?** Any team member can trigger the workflow. The `release-stable` GitHub Actions environment requires approval from a member of the `nmp_devops` team before the workflow proceeds.

---

## Overview

> The examples in this document use `0.1.2` as the version being released.

```
trigger release-stable.yaml with source_sha + version → nmp_devops approval → workflow tags source_sha → Platform-Deploy publishes to PyPI
```

Artifacts published on a stable release:
- `nemo-platform` on [pypi.org](https://pypi.org/project/nemo-platform/)
- `nemo-platform-plugin` on [pypi.org](https://pypi.org/project/nemo-platform-plugin/)

Nightly builds go to `pypi.nvidia.com` (NVIDIA's internal/public PyPI mirror), **not** public PyPI.

## Versioning model

Release and nightly wheel versions are resolved at build time. The release workflow runs `.github/scripts/stamp_sdk_version.py`, then passes the resolved version to Hatch through `UV_DYNAMIC_VERSIONING_BYPASS`.

Dynamic versioning is intentionally limited to packages that need release/nightly wheel metadata:
- `packages/nemo_platform` (`nemo-platform`)
- `packages/nemo_platform_plugin` (`nemo-platform-plugin`)
- `sdk/python/nemo-platform` (`nemo-platform-sdk`, consumed by the released wrappers and SDK tooling)

All other first-party workspace packages use static stub versions, normally `0.0.0`, because they are implementation packages rather than independently released artifacts. Do not add `nmp-dynamic-versioning` to another package unless that package is added to the release catalog or otherwise needs published wheel metadata.

`packages/nmp_build_tools` centralizes the Hatch version source and its defaults, but that package itself is also an internal stub-version package. The OpenAPI specs are schema inputs for SDK generation and intentionally keep a fixed `info.version: 0.0.0`; package release versions should not be copied into the specs.

---

## Step 1 — Choose the source SHA and release version

Pick the full 40-character commit SHA on `main` that should be released, plus the SemVer core version to publish, for example `0.1.2`. The stable workflow creates the release tag at `source_sha`, and the wheel build receives the package version from the workflow input.

If the API surface changed since the last SDK update, regenerate the OpenAPI spec and SDKs before releasing:

```bash
make update-sdk
```

This runs `make refresh-openapi` (regenerates `openapi/openapi.yaml` and plugin specs) and then syncs the Python and web SDKs via Stainless. Requires `STAINLESS_API_KEY` to be set — see `sdk/README.md` for setup instructions. The generated OpenAPI specs should keep `info.version: 0.0.0`.

To find the right SHA:

```bash
git log --oneline main | head -5
# Pick the commit to release and copy its full 40-character SHA.
```

---

## Step 2 — Trigger the stable release workflow

Navigate to the [`release-stable.yaml` workflow](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/release-stable.yaml) and click **Run workflow**.

| Input | Required | Description |
|---|---|---|
| `source_sha` | Yes | The full 40-character commit SHA to release from (must be on `main`). |
| `version` | Yes | SemVer core version string to release, e.g. `0.1.2`. This becomes the stable git tag and wheel version. |
| `release_date` | No | `YYYY-MM-DD`. Provide only on the first run for a given version; leave blank on reruns. |
| `release_scope` | No | `all` (default) releases every catalog SDK and container. Use `sdks`, `containers`, or `custom` for narrower releases. |
| `sdk_ids` | No | Comma-separated SDK IDs for `release_scope: custom`; must exist in `release/assets.yaml`. |
| `container_ids` | No | Comma-separated container IDs for `release_scope: custom`; must exist in `release/assets.yaml`. |

The workflow runs from the **`main` branch** by default. The `source_sha` must be reachable from that branch.

**What the workflow does:**
1. Validates inputs and previews the release.
2. Pauses at the `approve-stable-release` gate — a member of the **`nmp_devops` team** must approve in the GitHub environment UI.
3. Creates and pushes a git tag (e.g. `0.1.2`) at `source_sha`.
4. Builds Python wheels for each SDK in `release/assets.yaml` using `.github/actions/build-nemo-platform-wheel`.
5. Assembles a release bundle with checksums and metadata.
6. Dispatches a `release-bundle-produced` event to the **Platform-Deploy** repository (`CI_DISPATCH_REPO` secret), which handles the actual PyPI publish.

> If the PyPI publishing service is returning 5xx errors, the publish step in Platform-Deploy will fail. Wait for the service to recover and re-run the workflow with the same `source_sha` and `version` — the stable tag is already reserved so re-running is safe.

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

## Container image eligibility

The `container:` list in `release/assets.yaml` declares which container
images are eligible for release publishing. The bundle workflow records the
selected containers as `container`-typed entries in `release-manifest.json`,
and the release consumer stages those images after the SDK publish, reading
this list from this repository at the release ref. Eligibility is therefore
version-pinned: re-staging an old tag publishes the container set declared at
that commit.

`release_scope` controls what a release includes (default `all`):

| Scope | Includes |
| --- | --- |
| `all` | every catalog SDK + every catalog container (default) |
| `sdks` | every catalog SDK, no containers |
| `containers` | every catalog container, no SDKs |
| `custom` | exactly the comma-separated `sdk_ids` + `container_ids` (either may be empty) |

`custom` enables single-artifact or arbitrary-subset releases (for example a
patch release of one container via `release_scope: custom`,
`container_ids: nmp-automodel-tasks`); `containers` releases the whole
container set with no SDK wheels.

Adding an image here also requires a catalog metadata entry on the consumer
side. Images are built into the dev registry tagged with this repository's
commit SHA on every merge to main; release SHAs that predate that build
trigger need a manual image build first.

---

## Nightly builds

Nightly builds run automatically at 20:00 PT and publish to `pypi.nvidia.com`. They use the HEAD of `main` and version strings like `0.1.3.dev20260101120000`. No action required from the team.

To trigger a nightly manually: [`release-nightly.yaml`](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/release-nightly.yaml) → **Run workflow** (no inputs required). Leave `send_notifications` enabled for real reruns; disable it only for quiet smoke/ad-hoc runs.
