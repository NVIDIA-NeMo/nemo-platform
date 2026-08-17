// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { sanitizeEntityName, toValidEntityName } from '@nemo/common/src/utils/entityName';
import { FormField, TextInput } from '@nvidia/foundations-react-core';
import { useEffect, useRef, useState, type FC, type ReactNode } from 'react';
import { useDebounce } from 'use-debounce';

export interface EntityNameFieldProps {
  /** Lowercase entity noun used in copy, e.g. "secret", "fileset". */
  entity: string;
  /** Field label. Defaults to "Name". */
  label?: string;
  value: string;
  onChange: (value: string) => void;
  /**
   * Async uniqueness check. Resolve `true` if the sanitized name already
   * exists on another entity. Omit for entities with no uniqueness
   * requirement — the field then only runs local format validation.
   */
  checkAvailability?: (sanitizedName: string) => Promise<boolean>;
  debounceMs?: number;
  disabled?: boolean;
}

/**
 * Naming UX for entity create/rename forms — see
 * `web/.agents/skills/ui-design/references/entity-naming.md` for the
 * governing contract this component implements:
 *
 * 1. Live "Your {entity} will be created as {value}" preview as the user types.
 * 2. Sanitizes (spaces → dashes, lowercased) for that preview only — never
 *    rewrites the field's actual value.
 * 3. Local errors surface only after blur, and only when nothing valid can
 *    be salvaged from the input (e.g. it's empty or pure symbols) — cosmetic
 *    deviations (spaces, casing, stray characters) are silently fixed by the
 *    same sanitization used for submission, so they are never form errors.
 * 4. When `checkAvailability` is provided, uniqueness is checked on every
 *    keystroke (debounced): "Checking name..." while in flight, then a
 *    conflict error surfaces immediately (not gated on blur).
 */
export const EntityNameField: FC<EntityNameFieldProps> = ({
  entity,
  label = 'Name',
  value,
  onChange,
  checkAvailability,
  debounceMs = DEFAULT_DEBOUNCE_MS,
  disabled,
}) => {
  const [touched, setTouched] = useState(false);
  const [debouncedValue] = useDebounce(value, debounceMs);
  const [checking, setChecking] = useState(false);
  const [conflict, setConflict] = useState(false);
  const requestId = useRef(0);

  const sanitized = toValidEntityName(debouncedValue, '');

  useEffect(() => {
    if (!checkAvailability || !sanitized) {
      setChecking(false);
      setConflict(false);
      return;
    }

    const id = ++requestId.current;
    setChecking(true);
    checkAvailability(sanitized)
      .then((exists) => {
        if (requestId.current === id) {
          setConflict(exists);
        }
      })
      .finally(() => {
        if (requestId.current === id) {
          setChecking(false);
        }
      });
  }, [checkAvailability, sanitized]);

  const localError = !touched
    ? undefined
    : !value
      ? `${label} is required.`
      : sanitizeEntityName(value) === undefined
        ? `${label} must contain at least one letter or number.`
        : undefined;

  let slotHelp: ReactNode;
  let slotError: string | undefined;

  if (checking) {
    slotHelp = 'Checking name...';
  } else if (conflict) {
    slotError = `An ${entity} named ${sanitized} already exists`;
  } else if (localError) {
    slotError = localError;
  } else {
    const preview = toValidEntityName(value, '');
    slotHelp = preview ? (
      <>
        Your {entity} will be created as <span className="text-primary">{preview}</span>
      </>
    ) : undefined;
  }

  return (
    <FormField
      slotLabel={label}
      slotHelp={slotHelp}
      slotError={slotError}
      status={slotError ? 'error' : undefined}
    >
      <TextInput
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setTouched(true)}
      />
    </FormField>
  );
};
