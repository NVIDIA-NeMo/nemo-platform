// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { getEntityNameError, toValidEntityName } from '@nemo/common/src/utils/entityName';
import { FormField, TextInput } from '@nvidia/foundations-react-core';
import { useEffect, useRef, useState, type FC } from 'react';
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
 * 3. Local format errors surface only after blur.
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

  const localError = touched ? getEntityNameError(value, label) : undefined;

  let slotHelp: string | undefined;
  let slotError: string | undefined;

  if (checking) {
    slotHelp = 'Checking name...';
  } else if (conflict) {
    slotError = `An ${entity} named ${sanitized} already exists`;
  } else if (localError) {
    slotError = localError;
  } else {
    const preview = toValidEntityName(value, '');
    slotHelp = preview ? `Your ${entity} will be created as ${preview}` : undefined;
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
