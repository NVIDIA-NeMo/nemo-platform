# NeMo Platform Fern Docs

This directory holds the Fern MDX source for the NeMo Platform documentation site.

All new published docs edits should land under `fern/`. Keep the legacy MkDocs tree under `../docs/` as migration source material and historical reference.

## Quick Links

| What | Where |
| --- | --- |
| Fern dashboard | https://dashboard.buildwithfern.com (NVIDIA org) |
| Agent skill | [`../.claude/skills/nemo-platform-docs/SKILL.md`](../.claude/skills/nemo-platform-docs/SKILL.md) |
| CI workflows | [`../.github/workflows/fern-docs-*.yml`](../.github/workflows/) |
| Publish workflow | [`../.github/workflows/publish-fern-docs.yml`](../.github/workflows/publish-fern-docs.yml) |

## Quickstart

First time on this machine:

```bash
npx -y fern-api@latest login
```

Then run from `fern/`:

```bash
npm run check   # Validate docs.yml, navigation, and MDX
npm run dev     # Start local preview at http://localhost:3000
```

`package.json` intentionally shells out to `npx -y fern-api@latest`, so there is no install step for local docs work.

## Layout

```text
fern/
├── fern.config.json          # Fern organization + CLI version
├── package.json              # npm run check|dev|generate|preview
├── docs.yml                  # Site config, theme, assets, redirects, versions
├── main.css                  # NVIDIA theme overrides
├── assets/                   # Logos, shared SVGs, and page images
├── components/               # Custom TSX components
└── versions/
    ├── latest.yml            # Navigation tree
    └── latest/pages/         # MDX content and page-local assets
```

The site uses a single `Latest` version. `versions/latest.yml` defines the sidebar and maps each page file to its canonical route.

## Authoring

Add pages under `versions/latest/pages/` and wire them into `versions/latest.yml`.

Use front matter for the rendered page title:

```yaml
---
title: "Page Title"
description: ""
---
```

Do not add a duplicate first `# Page Title` heading when it matches the front matter `title`; Fern renders that title automatically.

Use Fern-native MDX components such as `<Note>`, `<Tip>`, `<Warning>`, `<Tabs>`, `<Cards>`, and `<Card>`. Do not reintroduce MkDocs Material syntax like `!!! note`, `=== "Tab"`, `--8<--`, or `<div class="grid cards" markdown>`.

## Internal Links

Use Fern's nav-derived canonical URLs:

```mdx
[Workspaces](/documentation/get-started/core-concepts/workspaces)
```

Avoid source-path links such as `/get-started/concepts/workspaces`, `/latest/get-started/concepts/workspaces`, and relative `.md` links. If a public URL changes, add a redirect in `docs.yml`.

## API Reference

The REST API reference is generated natively by Fern from the OpenAPI spec — no `<swagger-ui>` embed. Two pieces wire it up:

- `generators.yml` declares the spec: `api.specs[].openapi: ./openapi/openapi.yaml`.
- `versions/latest.yml` surfaces it with an `- api: API Reference` navigation node (under the **Reference** section).

`openapi/openapi.yaml` is a symlink to the repo-root `openapi/openapi.yaml` (the generated source of truth), so the reference tracks the Platform API automatically. Regenerate the spec with `make refresh-openapi` from the repo root, then run `npm run check`.

Fern groups endpoints by their OpenAPI tag in the sidebar (Customizer, Evaluator, Guardrails, …), which replaces the old per-service filter chips. Link to it from other pages with the nav URL `/documentation/reference/api-reference`.

## Gated (unready) features

Some features are not shipped yet and must be **fully excluded from the build** — not just hidden from the sidebar. Fern's `hidden: true` still builds and serves the page (reachable by direct URL and indexable), so it is **not** used for this. Instead, the gated pages are simply **left out of `versions/latest.yml`**: Fern only builds pages referenced in the navigation, so an omitted page is never built (it 404s and is not indexed). This matches the old MkDocs `hide_unready_docs` hook, which dropped the same files from the build.

The gated `.mdx` files stay in the repo so they remain maintained. The gated trees today are: `auth/`, `customizer/`, `safe-synthesizer/`, `set-up/` + `helm/`, `evaluator/benchmarks/`, plus individual pages (`evaluator/metrics/{job-management,results}`, `run-inference/tutorials/deploy-models`, `example-applications/`, `troubleshooting/{cluster-setup,customizer}`, `get-started/quickstart`).

Inbound links from visible pages into gated pages are **delinked to plain text** (not rewritten URLs), since the target is not built — otherwise they would be broken links.

### Automated delinking

The old MkDocs hook delinked those references automatically. Fern has no build hook, so `scripts/delink-gated.mjs` reproduces it. "Gated" is derived from the nav (any `.mdx` not in `versions/latest.yml`), so there is no second list to maintain.

- `npm run check:gated-links` — fails if any **published** page links into a gated page (runs as part of `npm run check`, so CI enforces it).
- `npm run fix:gated-links` — rewrites those links to plain text in place.

So if someone links into a gated section, CI flags it and one command delinks it — no hunting for dead links by hand. `npm run broken-links` (also run in CI) is the broader backstop for any other dead link.

One difference from the old MkDocs hook: that hook ran at build time and kept the link in the source, so re-publishing a page reactivated its inbound links automatically. This script delinks in the **source**, so the references become plain text. When you publish a feature, re-add the links you want from those plain-text references as part of the same step that moves the nav block (`check:gated-links` won't block you — it only flags live links that still point at gated pages). This keeps local `fern docs dev` honest (no build-time source rewriting) at the cost of re-linking on publish.

`gated-nav.yml` holds the ready-to-paste navigation blocks for the gated features (it is a reference only; Fern does not read it). **To publish a feature when it ships:** move its block from `gated-nav.yml` into `versions/latest.yml`, re-add any inbound links you want, then run `npm run check` and `npm run broken-links`.

## CI and Publishing

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `fern-docs-ci.yml` | trusted `pull-request/<n>` mirror branch | Run `npm run check` with `DOCS_FERN_TOKEN` available |
| `fern-docs-preview-build.yml` | `pull_request` touching `fern/**` | Upload PR `fern/` sources with no secrets |
| `fern-docs-preview-comment.yml` | successful preview build workflow run | Generate a Fern preview with `DOCS_FERN_TOKEN` and post/update the PR comment |
| `publish-fern-docs.yml` | `main`, `docs/v*` tag, or manual dispatch | Publish the Fern docs site |

Required secret: `DOCS_FERN_TOKEN`, generated with `fern token` from an account that can publish to the NVIDIA Fern organization.

PRs that touch `fern/**` get a shared preview URL posted as a comment after the two-part preview workflow finishes.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `HTTP 403` or organization access error | Sign in at https://dashboard.buildwithfern.com, then run `npx -y fern-api@latest login` again |
| `fern check` YAML error | Use 2-space indentation; make sure `path:` values are relative to `versions/latest.yml` |
| Page 404 in preview | Check that `versions/latest.yml` lists the page and links by canonical route |
| Broken internal link | Rewrite it to the nav-derived `/documentation/...` URL |
| JSX or MDX parse error | Escape raw `{}`, `<`, or `>` in prose, and use Fern components instead of raw MkDocs syntax |
