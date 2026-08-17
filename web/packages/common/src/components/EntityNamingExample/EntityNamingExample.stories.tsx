// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { sanitizeEntityName, toValidEntityName } from '@nemo/common/src/utils/entityName';
import { FormField, TextInput } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { useEffect, useState, type ChangeEvent, type FC, type ReactElement } from 'react';
import { useController, useForm } from 'react-hook-form';
import { useDebounce } from 'use-debounce';
import { z } from 'zod';

/**
 * This story is a worked example of the entity-naming UX contract from
 * `web/.agents/skills/ui-design/references/entity-naming.md` — it is NOT a
 * shared component. There is no `EntityNamingExample` export for product
 * code to import; every form implements this pattern itself with its own
 * `react-hook-form` + `zod` schema, exactly like `CreateInferenceProviderSidePanel`
 * or `CreateSecretModal` already do. Copy the shape, not the file.
 */
interface NameFormValues {
  name: string;
}

/**
 * Per-field schema for THIS interaction pattern — deliberately not
 * `entityNameSchema` from `entityName.ts`, which hard-fails on any cosmetic
 * deviation (case, spaces, stray characters). Here the deviation is fixed
 * silently by the `.transform`, so validation only rejects input that has
 * nothing salvageable left after sanitization.
 */
function buildNameSchema() {
  return z
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
}

/** Result of the debounced uniqueness check, tagged with the exact candidate it was checked against. */
type AvailabilityState = {
  candidate: string;
  status: 'checking' | 'available' | 'conflict' | 'failed';
};

interface NameFieldFormProps {
  entity: string;
  /** Resolve `true` when the sanitized name already exists on another entity. Omit for entities with no uniqueness requirement. */
  checkAvailability?: (sanitizedName: string) => Promise<boolean>;
  disabled?: boolean;
  defaultValue?: string;
  /** Surfaces the form's submitted (already-sanitized) `formData` for inspection in the story. */
  onSubmitted?: (values: NameFormValues) => void;
}

const NameFieldForm: FC<NameFieldFormProps> = ({
  entity,
  checkAvailability,
  disabled,
  defaultValue = '',
  onSubmitted,
}) => {
  const {
    control,
    watch,
    handleSubmit,
    formState: { errors, touchedFields },
  } = useForm<NameFormValues, unknown, NameFormValues>({
    resolver: zodResolver(z.object({ name: buildNameSchema() })),
    defaultValues: { name: defaultValue },
    mode: 'onBlur',
  });

  const {
    field: { value, onChange, onBlur },
  } = useController({ control, name: 'name' });

  const rawValue = watch('name');
  const [debouncedValue] = useDebounce(rawValue, DEFAULT_DEBOUNCE_MS);
  const sanitized = toValidEntityName(debouncedValue, '');

  // Uniqueness runs on every keystroke (debounced), independent of RHF's
  // `mode: 'onBlur'` gate on the local schema error — a conflict must
  // surface immediately, never wait for blur. Result is tracked by the
  // candidate it was checked against (not folded into RHF's error state)
  // so a resolve that lands after the user kept typing can never render
  // against a candidate it wasn't actually checked for.
  const [availability, setAvailability] = useState<AvailabilityState>();

  useEffect(() => {
    if (!checkAvailability) return;
    if (!sanitized) {
      // Nothing salvageable to check — drop any stale result rather than
      // let a prior conflict/failure linger for a candidate that no
      // longer exists.
      setAvailability(undefined);
      return;
    }
    let cancelled = false;
    setAvailability({ candidate: sanitized, status: 'checking' });
    checkAvailability(sanitized)
      .then((exists) => {
        if (cancelled) return;
        setAvailability({ candidate: sanitized, status: exists ? 'conflict' : 'available' });
      })
      .catch(() => {
        if (cancelled) return;
        setAvailability({ candidate: sanitized, status: 'failed' });
      });
    return () => {
      cancelled = true;
    };
  }, [checkAvailability, sanitized]);

  const preview = toValidEntityName(rawValue, '');
  // Only trust `availability` when it was checked against the candidate
  // currently on screen — otherwise it's a stale result for a value the
  // user has since changed.
  const currentAvailability = availability?.candidate === preview ? availability : undefined;
  const checking = currentAvailability?.status === 'checking';
  const conflict = currentAvailability?.status === 'conflict' ? currentAvailability : undefined;
  const checkFailed = currentAvailability?.status === 'failed';

  const schemaError = touchedFields.name ? errors.name?.message : undefined;
  const slotError = conflict
    ? `An ${entity} named ${conflict.candidate} already exists`
    : schemaError;
  const slotHelp = checking ? (
    'Checking name...'
  ) : slotError ? undefined : checkFailed ? (
    "Couldn't check name availability. You can still submit."
  ) : preview ? (
    <>
      Your {entity} will be created as <span className="text-primary">{preview}</span>
    </>
  ) : undefined;

  return (
    <form
      onSubmit={handleSubmit((values) => onSubmitted?.(values))}
      className="flex flex-col gap-density-md"
    >
      <FormField
        slotLabel="Name"
        slotHelp={slotHelp}
        slotError={slotError}
        status={slotError ? 'error' : undefined}
      >
        <TextInput
          value={value}
          disabled={disabled}
          autoComplete="off"
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.currentTarget.value)}
          onBlur={onBlur}
        />
      </FormField>
    </form>
  );
};

// Simulated backend: these names are "taken" by another entity, to exercise
// the uniqueness-conflict state without a real API.
const TAKEN_NAMES = ['my-fileset', 'production-secret'];

const fakeCheckAvailability = (name: string): Promise<boolean> => {
  const { promise, resolve } = Promise.withResolvers<boolean>();
  setTimeout(() => resolve(TAKEN_NAMES.includes(name)), 600);
  return promise;
};

const meta: Meta<typeof NameFieldForm> = {
  title: 'Common/Examples/Entity Naming',
  component: NameFieldForm,
  decorators: [
    (Story) => (
      <div className="w-[420px]">
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof NameFieldForm>;

/**
 * No uniqueness constraint. Type "Foo bar" or "MyProject" and watch the
 * description below the field update live, while the input itself keeps
 * exactly what you typed. Blur the field afterward — since the sanitized
 * name is what `handleSubmit` actually receives (via the zod `.transform`),
 * cosmetic differences like these never turn into a form error.
 */
export const renderDefault = (): ReactElement => <NameFieldForm entity="fileset" />;

export const Default: Story = {
  render: renderDefault,
};

/**
 * Blur with input that sanitizes to nothing usable (e.g. only symbols) to
 * see the one case that *does* error after blur — there's no valid name to
 * submit.
 */
export const renderNothingValidToSubmit = (): ReactElement => (
  <NameFieldForm entity="fileset" defaultValue="!!!" />
);

export const NothingValidToSubmit: Story = {
  render: renderNothingValidToSubmit,
};

/**
 * Uniqueness enforced via `checkAvailability`. Type "my-fileset" or
 * "production-secret" to see "Checking name..." while the debounced query
 * is in flight, then the "already exists" error — surfaced immediately,
 * without needing to blur.
 */
export const renderWithUniquenessCheck = (): ReactElement => (
  <NameFieldForm entity="fileset" checkAvailability={fakeCheckAvailability} />
);

export const WithUniquenessCheck: Story = {
  render: renderWithUniquenessCheck,
};

/** Disabled field, e.g. renaming an entity that doesn't support it. */
export const renderDisabled = (): ReactElement => (
  <NameFieldForm entity="dataset" defaultValue="my-dataset" disabled />
);

export const Disabled: Story = {
  render: renderDisabled,
};
