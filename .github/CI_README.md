# GitHub Automation Docs

This directory contains the repository's GitHub automation: workflow files,
reusable actions, and supporting docs.

## What Lives Here

- `workflows/`
  GitHub Actions workflow definitions for source validation, Studio CI, GPU
  tests, semantic PR checks, and releases.

- `actions/`
  Local composite actions shared across workflows.

## Workflow Overview

### CI Check Workflows

- `ci.yaml`
  Main Python unit/integration/lint CI workflow. Parts of this must pass for
  merge. On successful `main` pushes, it also sends a generic completion event
  to an external CI consumer.

- `studio-ci.yaml`
  Frontend/Studio CI workflow.

- `semantic-pull-requests.yaml`
  Pull request title validation.

### Deployment and Release Workflows

- `release*.yaml`
  Nightly, RC, and stable release orchestration. These consume a reusable workflow file to minimize
  duplication.

## GitHub Apps

- DCO app
  Developer Certificate of Origin (DCO) checks are handled by the installed DCO
  app, not by a repository workflow.
