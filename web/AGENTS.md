# Studio Agent Instructions

## Project Context

- NeMo Studio — React + TypeScript monorepo for the NeMo Platform UI
- Tech Stack: React 18, TypeScript, Vite, Vitest, Playwright, pnpm workspaces
- Uses KUI (Kaizen UI) React components, TanStack Query

## Agent skills

Cursor/Claude skills for this monorepo live under **`web/.agents/skills/`** (for example `unit-test`, `e2e-test`, `feature-flags`, `ux-guidelines`, `visual-dev`, `test-coverage-improvement`).

## Package Overview

- **packages/studio** — Main React frontend application
- **packages/common** — Shared code between UI and service
- **packages/sdk** — Generated API clients and types
- **packages/sandbox** — Development tools
- **packages/storybook** — Component stories and documentation
- **packages/scripts** — Build scripts and utilities

## Import Path Rules

- **Never use relative imports.** This applies to sibling files in the same directory too. Always use the absolute alias path — even `./useSomething` or `./types` should be written as `@studio/components/Foo/useSomething` or `@nemo/common/src/utils/types`. ESLint (`no-relative-import-paths/no-relative-import-paths`) enforces this and will warn if you slip.
- Import path mappings:
  - `@studio/` → `packages/studio/src/` (inside the studio package)
  - `@nemo/common/` → `packages/common/src/`
  - `@nemo/sdk` → `packages/sdk/`
- Use `import type` for type-only imports

## Package Management

- Use **pnpm** exclusively — never npm or yarn
- Run frontend commands from `web/`, not from repo root
- Install dependencies: `pnpm add <package>`
- Run scripts: `pnpm <script-name>`

## Running Tests Locally

- **Never invoke `vitest` directly** (e.g. `pnpm vitest --run`). Always go through a package's `test` script so env/config (e.g. `NODE_OPTIONS=--max-old-space-size=10240` in `studio`) is applied.
- Use one of these patterns from `web/`:
  - Whole package: `pnpm --filter <package-name> test` (e.g. `pnpm --filter nemo-studio-ui test`, `pnpm --filter @nemo/common test`)
  - Targeted file: `pnpm --filter <package-name> test path/to/file.test.tsx`

## CI Scripts Convention

CI automatically discovers and runs specific scripts from each package's `package.json`. To opt a package into CI checks, add these scripts:

- **`test:ci`** — Runs tests in CI. Use this for CI-specific config like coverage, reporters, and non-watch mode (e.g., `vitest run --coverage`).
- **`typecheck`** — Runs type checking (`tsc --noEmit`). The same script runs locally and in CI — no separate `typecheck:ci` needed.

If a package defines these scripts, CI will pick them up automatically. No additional CI yaml configuration is required.

## TypeScript Standards

### Type Safety

- **Never use `any`** — use `unknown` and type guards instead
- Prefer `interface` over `type` for object shapes and contracts
- Use `type` for unions, intersections, and computed types
- Implement strict null checks and handle undefined/null explicitly
- Use type assertions sparingly — prefer type guards and narrowing

### Naming Conventions

- `camelCase` for variables, functions, and methods
- `PascalCase` for classes, interfaces, types, and React components
- `SCREAMING_SNAKE_CASE` for constants and environment variables

### Interface and Type Definitions

- Use descriptive property names with clear types
- Mark optional properties with `?` and provide defaults when appropriate
- Use `readonly` for immutable properties

### Functions

- Prefer arrow functions for short, pure functions
- Use function declarations for hoisted functions and methods
- Keep functions small and focused (Single Responsibility Principle)
- Use explicit return types for public APIs and complex functions

### Error Handling

- Use Result types or discriminated unions for predictable errors
- Throw exceptions only for truly exceptional circumstances
- Implement proper error boundaries in React components

### Imports and Exports

- Use named exports over default exports
- Group imports: external libraries, internal modules, relative imports
- Use absolute imports via tsconfig path mapping (never relative)

### React Patterns

- Define explicit props interfaces for all components
- Use generic components for reusable UI patterns
- Use discriminated unions for variant props

### Code Organization

- One class or main function per file
- Co-locate related types with their implementations
- Organize by feature/domain, not by technical layer
