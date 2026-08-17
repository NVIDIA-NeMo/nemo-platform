<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Entity Naming UX

Every "name this entity" field follows the same interaction contract. Do not
invent per-form validation timing, per-form sanitization copy, or a bespoke
uniqueness check — reuse the pattern below.

> Canonical helpers: `packages/common/src/utils/entityName.ts`
> (`ENTITY_NAME_REGEXP`, `ENTITY_NAME_HELP`, `sanitizeEntityName`,
> `toValidEntityName`, `getEntityNameError`, `entityNameSchema`). Read that
> file before adding a parallel regex/sanitizer.

## The contract

1. **Live preview description.** As the user types, `slotHelp` (below the
   field, not `slotError`) shows what will actually be created:

   ```
   Your {entity} will be created as {value}
   ```

   Compute `{value}` by running the current input through
   `toValidEntityName(input, fallback)` — never re-derive sanitization ad hoc.
   `{entity}` is the lowercase entity noun ("secret", "fileset", "provider").
   Render this specific message with `text-primary` (it reads as confirmed
   fact, not muted helper copy) — `"Checking name..."` and error messages
   keep the field's default helper/error color.

2. **Sanitize for preview only, never the field.** If the typed value doesn't
   satisfy `ENTITY_NAME_REGEXP`, don't rewrite the input the user sees or
   types into — only the *description* reflects the sanitized name:
   - Spaces become dashes: `"Foo bar"` → `"foo-bar"`.
   - Case is lowercased: `"FooBar"` → `"foobar"`.
   - Other invalid characters, leading non-letters, and repeated/trailing
     dashes are stripped per `sanitizeEntityName`.

   The field's actual value is whatever the user typed; the sanitized string
   is what gets submitted and is what the "will be created as" copy shows.

3. **No error state before blur — and even after blur, only for
   unsalvageable input.** The submitted value is always the *sanitized*
   name, not the literal typed value, so a cosmetic deviation (spaces,
   casing, a stray invalid character) is never a form error — it's exactly
   what the "will be created as" preview already resolves for the user.
   Don't set `status="error"` / `slotError` while the field has focus.
   `onBlur` (react-hook-form: check `fieldState.isTouched`), surface
   `slotError` **only** when `sanitizeEntityName(value)` returns
   `undefined` — i.e. nothing valid survives sanitization (empty input, or
   input that is pure symbols/too short once invalid characters are
   stripped). In every other case, blur shows the same "will be created as"
   `slotHelp` as while typing.

4. **Uniqueness check runs on every keystroke, not just blur.** For entities
   whose name must be unique, debounce the typed value (`use-debounce`,
   `DEFAULT_DEBOUNCE_MS`) and query for a conflict as the user types:
   - While the debounced query is in flight: `slotHelp` = `"Checking name..."`
     (replaces the "will be created as" copy for that moment; don't show both).
   - If the sanitized name already exists on another entity: treat it as an
     error immediately — this one does **not** wait for blur, since it's the
     one thing the live preview can't tell the user on its own. Show
     `slotError` = `"An {entity} named {value} already exists"`, where
     `{value}` is the sanitized (would-be-submitted) name, and set
     `status="error"`.
   - If available: fall back to the normal "will be created as" `slotHelp`.

## State precedence for the field

Evaluate in this order — the first match wins:

| Condition | `slotHelp` / `slotError` | `status` |
| --- | --- | --- |
| Uniqueness query in flight | `slotHelp`: "Checking name..." | none |
| Uniqueness query resolved: conflict found | `slotError`: "An {entity} named {value} already exists" | `error` |
| Field touched (blurred) and `sanitizeEntityName(value)` is `undefined` (nothing salvageable) | `slotError`: "{label} is required." / "{label} must contain at least one letter or number." | `error` |
| Otherwise | `slotHelp`: "Your {entity} will be created as {value}" (`text-primary`) | none |

## Example

```tsx
const [name, setName] = useState('');
const [touched, setTouched] = useState(false);
const [debouncedName] = useDebounce(name, DEFAULT_DEBOUNCE_MS);

const sanitized = toValidEntityName(debouncedName, '');
const { data: conflict, isFetching: isChecking } = useCheckNameAvailability(sanitized, {
  enabled: sanitized.length > 0,
});

const localError = !touched
  ? undefined
  : !name
    ? 'Name is required.'
    : sanitizeEntityName(name) === undefined
      ? 'Name must contain at least one letter or number.'
      : undefined;

const slotHelp = isChecking ? (
  'Checking name...'
) : !conflict && !localError ? (
  <span className="text-primary">Your secret will be created as {toValidEntityName(name, '')}</span>
) : undefined;

const slotError = conflict
  ? `A secret named ${sanitized} already exists`
  : localError;

<FormField
  slotLabel="Name"
  slotHelp={slotHelp}
  slotError={slotError}
  status={slotError ? 'error' : undefined}
>
  <TextInput value={name} onChange={(e) => setName(e.target.value)} onBlur={() => setTouched(true)} />
</FormField>;
```

## Do / Don't

- **Do** reuse `sanitizeEntityName` / `toValidEntityName` for the preview
  string. **Don't** hand-roll a `.replace(/\s+/g, '-').toLowerCase()` per
  form — it will drift from `ENTITY_NAME_REGEXP`.
- **Do** leave the input's literal value untouched while typing. **Don't**
  rewrite `field.value` to the sanitized string as the user types — that
  fights cursor position and hides what they actually typed.
- **Do** gate local validation errors on `isTouched`/`onBlur`, and only for
  input `sanitizeEntityName` can't salvage. **Don't** surface
  `getEntityNameError`'s cosmetic messages ("must be lowercase", "cannot
  contain spaces") as blur errors — those are auto-fixed at submit, not
  user mistakes. **Don't** gate the uniqueness-conflict error on blur —
  surface it as soon as the debounced query resolves.
- **Do** debounce the uniqueness query (`use-debounce`). **Don't** fire a
  request on every raw keystroke.