# UI Package Agent Instructions

## About This Package

- Main React frontend application for NeMo Studio
- Built with React 18, TypeScript, Vite
- Handles user interfaces for model customization, evaluation, and deployment
- Integrates with backend APIs through generated SDK clients

## Design System

- **Use NVIDIA Foundations React as the primary design system** — preferred over custom components
- NVIDIA Foundations React provides consistent styling, accessibility, and user experience patterns
- Follow NVIDIA Foundations React's design tokens and theming system for consistent visual design
- Leverage NVIDIA Foundations React's built-in accessibility features and ARIA patterns

## Key Dependencies

- **NVIDIA Foundations React** (@nvidia/foundations-react-core) — Primary component library
- **TanStack Query** — Data fetching and caching
- **React Hook Form + Zod** — Form handling and validation
- **React Router 6** — Client-side routing

## Import Path Rules

- **Never use relative imports** — always use absolute imports
- Import path mappings:
  - `@studio/` → `packages/studio/src/`
  - `@e2e-tests/` → `packages/studio/e2e-tests/`
- Other local packages are imported via pnpm workspaces

### KUI v1 Select: always wrap items in SelectListbox

In KUI v1, `SelectContent` is a transparent popover host — it has no background.
Background, border, and shadow come from `SelectListbox` → `MenuRoot` internally.

**Required pattern:**

```tsx
<SelectContent>
  <SelectListbox>
    <SelectItem value="a">A</SelectItem>
  </SelectListbox>
</SelectContent>
```

Wrong — transparent dropdown:

```tsx
<SelectContent>
  <SelectItem value="a">A</SelectItem> {/* no SelectListbox = no background */}
</SelectContent>
```

Exception: call sites that fill SelectContent with custom children containing their
own background (e.g. a sticky Block with bg-surface) are fine as-is.

### KUI form gotchas — the silent-failure set

Each compiles, lints and typechecks clean, then renders nothing wrong — the element is
simply inert or invisible.

**`slotError` needs `status="error"` to render.** Without a status `FormField` shows
`slotHelp` instead and drops the message. `Controlled*` wrappers set status from
react-hook-form only, so any other error source must set it too (`formFieldProps` spreads
last, so it wins):

```tsx
formFieldProps={{ slotError: fieldError, status: fieldError ? 'error' : undefined }}
```

**`FormModal.disabled` blocks closing.** It means "busy": it kills Cancel and stops
`handleUserClose`, trapping the user. For validation use `submitDisabled`.

```tsx
disabled={isPending}         // busy → intentionally locked
submitDisabled={!isValid}    // invalid → submit blocked, dismiss still works
```

**`Text` has no `color="danger"`, and `text-danger` is not an emitted utility.** `danger`
exists only on `Button`; the token is `--text-color-feedback-danger`. Devtools showing
**"Inherited from"** means no rule matched at all, not that yours lost a specificity fight.

```tsx
<Text className="text-[var(--text-color-feedback-danger)]">…</Text>
```

**Modals seeded from a prop must re-seed on `open`.** `useForm({ defaultValues })` reads
once at mount; a persistently-rendered modal mounts before the prop exists and keeps the
empty default forever. Callers passing a constant work by accident, so the bug arrives
with the second caller.

```tsx
useEffect(() => {
  resetForm(makeDefaultValues(agentProp)); // NOT `if (!open)` — that only resets on close
}, [open, agentProp, resetForm]);
```
