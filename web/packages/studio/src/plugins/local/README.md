# Local-only Studio plugins (optional)

Gitignored overrides for plugins **not** in this PR. The committed examples live in
`web/packages/studio-plugins-example/`.

To add private plugins on top of the example package:

1. Add modules under this directory (gitignored).
2. Register them in gitignored `../manifest.local.ts` (merged after core, before external).
