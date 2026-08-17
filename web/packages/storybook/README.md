<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Studio Storybook

Storybook 10 for developing and testing components from `packages/studio`, `packages/common`, and `packages/sandbox`.

## Run

From repo root:

```bash
pnpm storybook
```

Or from this package:

```bash
pnpm storybook
```

Opens at http://localhost:6006.

## Adding stories

Add `*.stories.tsx` (or `*.stories.ts`) next to components in:

- `packages/studio/src/**`
- `packages/common/src/**`
- `packages/sandbox/**`

Stories are discovered automatically; path aliases `@studio/*` and `@nemo/common/*` resolve as in the main app.

## Optional

Storybook is not required for CI or production build. To remove it completely, update these locations:

- **This package** — Delete the `packages/storybook/` directory.
- **Root package** — In `package.json` at the repo root (`web/package.json`), remove the `storybook` script.
- **Workspace catalog** — In `pnpm-workspace.yaml`, remove from the `catalog` section: `@storybook/react`, `@storybook/react-vite`, and `storybook`.
- **studio package** — In `packages/studio/package.json`, remove the `@storybook/react` devDependency (only needed for `*.stories.tsx`).
- **common** - In `packages/common/package.json`, remove the `@storybook/react` devDependency (only needed for `*.stories.tsx`).
- **ESLint** — In `eslint.config.js`, remove the block that targets `**/*.stories.@(ts|tsx)` (e.g. the override that turns off `import/no-default-export` for story files).
- **Docs** — In `DEVELOPMENT.md`, remove or adjust the “Run Storybook” and “To remove Storybook later” instructions.

Then run `pnpm install` so the lockfile no longer references Storybook. If you also remove all `*.stories.tsx` files from `packages/studio`, `packages/common`, and `packages/sandbox`, the ESLint story override is unnecessary.
