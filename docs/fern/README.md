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

The API reference page lives at `versions/latest/pages/api/index.mdx` and renders `versions/latest/pages/api/openapi.yaml` with:

```mdx
<swagger-ui src="./openapi.yaml" />
```

Regenerate or replace `openapi.yaml` when the Platform API changes, then run `npm run check`.

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
