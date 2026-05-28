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
