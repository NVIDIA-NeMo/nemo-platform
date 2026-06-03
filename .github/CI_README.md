# GitHub Automation Docs

This directory contains the repository's GitHub automation: workflow files,
reusable actions, and supporting docs.

## What Lives Here

- `workflows/`
  GitHub Actions workflow definitions for source validation, Studio CI,
  documentation, security scanning, semantic PR checks, DCO merge-queue
  handling, and releases.

- `actions/`
  Local composite actions shared across workflows: change detection, policy
  WASM builds, disk cleanup, and self-hosted runner metadata.

## Workflow Overview

### CI Check Workflows

- `ci.yaml`
  Main source validation workflow. It runs linting, OPA policy WASM build,
  Python unit tests, Python integration tests, OPA policy tests, and PR
  coverage comments. It runs on pushes to `main`, pull requests to `main`,
  merge queue checks, and manual dispatch. On successful `main` pushes, it
  also sends a completion event to an external CI consumer.

- `studio-ci.yaml`
  Frontend/Studio workflow. It runs Studio type checks, tests, formatting,
  linting, dependency checks, and scripts checks for relevant web changes.
  Studio UI E2E tests run only on manual dispatch.

- `security.yaml`
  Security workflow. It runs TruffleHog secrets scanning and CodeQL analysis on
  pushes to `main`, pull requests to `main`, and manual dispatch. It also runs
  in merge queues so required checks can resolve, but the TruffleHog job
  intentionally skips its scan for `merge_group` events.

- `docs.yaml`
  Documentation workflow. It builds docs for relevant docs changes, deploys
  GitHub Pages on `main` pushes, tag pushes, and manual dispatch, deploys PR
  previews for same-repository PRs, and cleans up PR previews when those PRs
  close.

- `semantic-pull-requests.yaml`
  Pull request title validation.

- `request-nvskills-ci.yml`
  Dispatches the internal NVSkills validation workflow when a maintainer or
  admin comments `/nvskills-ci` on a pull request with changes under `skills/`.
  It also handles the trusted signature push from the NVSkills signing bot.

- `require-nvskills-ci.yml`
  Merge-blocking PR check for `skills/` changes. It passes immediately when a
  PR does not touch `skills/`. When `skills/` files changed, it requires the PR
  head commit to be the trusted NVSkills signature commit from
  `NVSKILLS_SIGNATURE_PUSH_ACTOR` (default `svc-nvskills-signing`) with commit
  title prefix `NVSKILLS_SIGNATURE_COMMIT_TITLE` (default
  `Attach NVSkills validation signatures`). If new `skills/` content is pushed
  after signing, a maintainer or admin must rerun `/nvskills-ci`. Repository
  admins must make `Require NVSkills CI for skill changes / require-nvskills-ci`
  a required check in branch protection or rulesets for this workflow to block
  merges. Internal pipeline/log lookup is documented in the NVIDIA onboarding
  doc section:
  <https://nvidia.atlassian.net/wiki/spaces/GAIT/pages/3483240468/Github+First+-+Outbound+Repos+Onboarding+doc+-+NVCARPS#Review-Internal-Pipeline-Logs>.

- `dco-war.yaml`
  Merge queue compatibility shim for the DCO check. Normal DCO validation comes
  from the installed DCO app.

### Deployment and Release Workflows

- `release-nightly.yaml`
  Scheduled and manually dispatched nightly release orchestration.

- `release-rc.yaml`
  Manually dispatched release candidate orchestration.

- `release-stable.yaml`
  Manually dispatched stable release orchestration. It includes a preview step
  and requires the `release-stable` environment approval before producing the
  release bundle.

- `release-bundle.yaml`
  Reusable release implementation shared by nightly, RC, and stable workflows.
  It validates release inputs, creates release tags when needed, builds SDK
  wheels, assembles the release bundle artifact, and dispatches the downstream
  release handoff event.

## GitHub Apps

- DCO app
  Developer Certificate of Origin (DCO) checks are handled by the installed DCO
  app, not by a repository workflow. The `dco-war.yaml` workflow exists only
  because the DCO app does not currently understand merge queue checks. The
  ruleset allows any source named `DCO` to satisfy the required check so merge
  queue entries can pass. When the DCO app supports merge queues, change the
  ruleset to require the app-owned DCO check instead and remove the workaround.
