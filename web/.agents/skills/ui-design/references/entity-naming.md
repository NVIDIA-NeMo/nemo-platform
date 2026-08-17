<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Entity Naming UX

Every "name this entity" field follows the same interaction contract. This is
a **pattern to implement per form**, not a shared component to import. Do not invent per-form validation timing, per-form sanitization copy, or a bespoke uniqueness check — reuse the shapes below.

> Canonical helpers: `packages/common/src/utils/entityName.ts`
> (`ENTITY_NAME_REGEXP`, `ENTITY_NAME_HELP`, `sanitizeEntityName`,
> `toValidEntityName`, `getEntityNameError`, `entityNameSchema`). Read that
> file before adding a parallel regex/sanitizer.
>
> Worked example: `packages/common/src/components/EntityNamingExample/EntityNamingExample.stories.tsx`
> (Storybook: **Common/Examples/Entity Naming**) renders this exact contract
> with `react-hook-form` + `zod`, end to end. It exists to demonstrate and
> visually validate the pattern — it is not exported for reuse. Copy the
> shape into your form; don't import the story file.

## The contract

1. **Live preview description.** As the user types, `slotHelp` (below the
   field, not `slotError`) shows what will actually be created:

   ```
   Your {entity} will be created as {value}
   ```

   Compute `{value}` from the live (untransformed) field value —
   `toValidEntityName(watch('name'), '')` — never re-derive sanitization ad
   hoc. `{entity}` is the lowercase entity noun ("secret", "fileset",
   "provider"). Render just the `{value}` token in `text-primary` — wrap only
   the sanitized name in a `<span>`, not the surrounding sentence — since it
   reads as confirmed fact, unlike the muted framing copy around it.
   `"Checking name..."` and error messages keep the field's default
   helper/error color.

2. **Sanitize for preview and submission, never the live field.** The input
   the user sees and types into is never rewritten — no cosmetic
   auto-correction as they type:
   - Spaces become dashes: `"Foo bar"` → `"foo-bar"`.
   - Case is lowercased: `"FooBar"` → `"foobar"`.
   - Other invalid characters, leading non-letters, and repeated/trailing
     dashes are stripped per `sanitizeEntityName`.

   That sanitized string is what the "will be created as" preview shows, and
   — via the schema's `.transform` above — what actually reaches your
   `onSubmit`/API call as `formData.name`. `watch()`/the field's own `value`
   always mirrors the user's literal keystrokes.

3. **No error state before blur — and even after blur, only for
   unsalvageable input.** Since the submitted value is always the _sanitized_
   name (never the literal typed value), a cosmetic deviation (spaces,
   casing, a stray invalid character) is never a form error — it's exactly
   what the "will be created as" preview already resolves for the user. Use
   `mode: 'onBlur'` on `useForm` for this field's form (or, in a
   multi-field form where other fields need different timing, gate the
   rendered `slotError` on `formState.touchedFields.name`) so the schema's
   `superRefine` error — "nothing salvageable" — only appears after the
   field has been blurred at least once. In every other case, blur shows the
   same "will be created as" `slotHelp` as while typing.

4. **Uniqueness check runs on every keystroke, not just blur, and is
   independent of the schema/blur gating above.** For entities whose name
   must be unique, debounce the live (`watch()`) value (`use-debounce`,
   `DEFAULT_DEBOUNCE_MS`) and query for a conflict as the user types. Track
   the result as an object tagging the checked candidate with its outcome —
   `checking`, `available`, `conflict`, or `failed` — in local `useState`,
   never folded straight into `formState.errors` via
   `setError`/`clearErrors` keyed only on the latest debounce, since an
   in-flight promise can resolve after the user has kept typing:
   - Before rendering a result, compare its `candidate` against the
     _current_ sanitized preview (`toValidEntityName(watch('name'), '')`).
     A mismatch means the result is stale for a value the user has since
     changed — discard it (render as if no check has run) rather than show
     it.
   - If the current value is unsalvageable (`sanitized` is empty): drop any
     stored result immediately, don't leave a prior conflict/failure
     rendered against a candidate that no longer exists.
   - While the debounced query is in flight: `slotHelp` = `"Checking name..."`
     (replaces the "will be created as" copy for that moment; don't show both).
   - If the sanitized name already exists on another entity: treat it as an
     error immediately — this one does **not** wait for blur, since it's the
     one thing the live preview can't tell the user on its own. Show
     `slotError` = `"An {entity} named {value} already exists"`, where
     `{value}` is the sanitized (would-be-submitted) name, and set
     `status="error"`.
   - If the check itself fails (rejected promise/network error): don't
     silently swallow it into an unhandled rejection, and don't render the
     normal "will be created as" preview either — that would claim an
     availability you never actually confirmed. Show a neutral
     non-blocking `slotHelp` (e.g. "Couldn't check name availability. You
     can still submit.") instead.
   - If available: fall back to the normal "will be created as" `slotHelp`.
   - If the full candidate list is already loaded client-side (as in
     `CreateInferenceProviderSidePanel`'s `existingNames` set), a debounced
     network call isn't needed — checking membership in the set on every
     keystroke satisfies the same "immediate, not blur-gated" requirement
     with less latency. Prefer that when the data's already in memory.

## State precedence for the field

Evaluate in this order — the first match wins:

| Condition                                                                                    | `slotHelp` / `slotError`                                                                    | `status` |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------- |
| Uniqueness check in flight for the current candidate                                         | `slotHelp`: "Checking name..."                                                              | none     |
| Uniqueness check resolved for the current candidate: conflict found                          | `slotError`: "An {entity} named {value} already exists"                                     | `error`  |
| Field touched (blurred) and `sanitizeEntityName(value)` is `undefined` (nothing salvageable) | `slotError`: "{label} is required." / "{label} must contain at least one letter or number." | `error`  |
| Uniqueness check for the current candidate failed (rejected)                                 | `slotHelp`: "Couldn't check name availability. You can still submit."                       | none     |
| Otherwise (including a stale/mismatched check result)                                        | `slotHelp`: "Your {entity} will be created as {value}" (`{value}` in `text-primary`)        | none     |

## Example

```tsx
const nameSchema = z
  .string()
  .superRefine((value, ctx) => {
    if (sanitizeEntityName(value) === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: value ? 'Name must contain at least one letter or number.' : 'Name is required.',
      });
    }
  })
  .transform((value) => toValidEntityName(value, value));

const {
  control,
  watch,
  handleSubmit,
  formState: { errors },
} = useForm({
  resolver: zodResolver(z.object({ name: nameSchema })),
  defaultValues: { name: '' },
  mode: 'onBlur',
});

const {
  field: { value, onChange, onBlur },
} = useController({ control, name: 'name' });

const rawValue = watch('name');
const [debouncedValue] = useDebounce(rawValue, DEFAULT_DEBOUNCE_MS);
const sanitized = toValidEntityName(debouncedValue, '');

// Tagged with the exact candidate it was checked against, so a resolve
// that lands after the user kept typing never gets rendered as current.
const [availability, setAvailability] = useState(undefined);

useEffect(() => {
  if (!sanitized) {
    setAvailability(undefined);
    return;
  }
  let cancelled = false;
  setAvailability({ candidate: sanitized, status: 'checking' });
  checkAvailability(sanitized)
    .then((exists) => {
      if (!cancelled)
        setAvailability({ candidate: sanitized, status: exists ? 'conflict' : 'available' });
    })
    .catch(() => {
      if (!cancelled) setAvailability({ candidate: sanitized, status: 'failed' });
    });
  return () => {
    cancelled = true;
  };
}, [sanitized]);

const preview = toValidEntityName(rawValue, '');
// Discard a result that no longer matches what's on screen.
const current = availability?.candidate === preview ? availability : undefined;
const checking = current?.status === 'checking';
const conflict = current?.status === 'conflict' ? current : undefined;
const checkFailed = current?.status === 'failed';

const slotError = conflict
  ? `A secret named ${conflict.candidate} already exists`
  : errors.name?.message;
const slotHelp = checking
  ? 'Checking name...'
  : slotError
    ? undefined
    : checkFailed
      ? "Couldn't check name availability. You can still submit."
      : preview && (
          <>
            Your secret will be created as <span className="text-primary">{preview}</span>
          </>
        );

<FormField
  slotLabel="Name"
  slotHelp={slotHelp}
  slotError={slotError}
  status={slotError ? 'error' : undefined}
>
  <TextInput value={value} onChange={(e) => onChange(e.currentTarget.value)} onBlur={onBlur} />
</FormField>;

// formData.name in handleSubmit is already sanitized — no extra step needed:
<form
  onSubmit={handleSubmit((formData) =>
    createSecret({ name: formData.name /* already sanitized */ })
  )}
/>;
```

## Do / Don't

- **Do** implement this per form, wired to its own `react-hook-form` +
  `zod` setup. **Don't** reach for a shared `EntityNameField`-style
  component — none exists, and none should; the Storybook example is
  reference material, not an import target.
- **Do** define a dedicated, per-field schema (`superRefine` +
  `sanitizeEntityName` + `.transform(toValidEntityName)`) for a field
  adopting this contract. **Don't** reuse `entityNameSchema` for it — that
  schema is for forms that intentionally hard-reject any raw-value deviation
  and don't want this softer UX.
- **Do** let the zod `.transform` produce the sanitized `formData.name` your
  submit handler receives. **Don't** manually re-sanitize in `onSubmit` — if
  you find yourself doing that, the schema is missing its `.transform`.
- **Do** reuse `sanitizeEntityName` / `toValidEntityName` for the preview
  string. **Don't** hand-roll a `.replace(/\s+/g, '-').toLowerCase()` per
  form — it will drift from `ENTITY_NAME_REGEXP`.
- **Do** leave the input's literal value (`watch()`/the controller's `value`)
  untouched while typing. **Don't** rewrite it to the sanitized string as the
  user types — that fights cursor position and hides what they actually typed.
- **Do** gate the schema's local error on `mode: 'onBlur'` (or
  `formState.touchedFields`), and only for input `sanitizeEntityName` can't
  salvage. **Don't** surface `getEntityNameError`'s cosmetic messages ("must
  be lowercase", "cannot contain spaces") as blur errors — those are
  auto-fixed at submit, not user mistakes. **Don't** gate the
  uniqueness-conflict error on blur — render it as soon as the debounced
  check resolves for the currently-displayed candidate.
- **Do** debounce the uniqueness check (`use-debounce`), or check against an
  already-loaded client-side set when one exists. **Don't** fire a network
  request on every raw keystroke.
