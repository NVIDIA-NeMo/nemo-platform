# Development Workflow

## Git Hooks

This project uses automated git hooks to maintain code quality.

### Pre-Commit Hook

Runs linting and formatting on staged files before each commit.

**What it does:**

- Executes `lint-staged` which runs ESLint and Prettier on staged TypeScript, JavaScript, and other files
- Automatically fixes and formats code when possible
- Configured in `lint-staged.config.js`

**Bypass if needed:**

```bash
git commit --no-verify
```

### Pre-Push Hook

Runs type checking across all packages before pushing to remote.

**What it does:**

- From `web/`, executes `pnpm --filter="...[origin/main]" run --parallel --if-present typecheck`
- Runs the native TypeScript 7 compiler (`tsc`), matching CI
- Prevents pushing code with type errors

**Bypass if needed:**

```bash
git push --no-verify
```

## Storybook (optional)

Storybook is available for developing and testing UI and common components in isolation. It is **optional** and not required for CI or production build.

**Run Storybook:**

- From repo root: `pnpm storybook`
- From the storybook package: `cd packages/storybook && pnpm storybook`

Storybook runs at http://localhost:6006.

**Where to add stories:** Add `*.stories.tsx` (or `*.stories.ts`) next to components under:

- `packages/ui/src`
- `packages/common/src`
- `packages/sandbox`

To remove Storybook later: delete `packages/storybook`, remove the `storybook` script from root `package.json`, and any Storybook-specific ESLint overrides; CI and main app build are unaffected.
