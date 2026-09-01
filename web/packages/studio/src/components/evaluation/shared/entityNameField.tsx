// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { sanitizeEntityName, toValidEntityName } from '@nemo/common/src/utils/entityName';
import { z } from 'zod';

/** An entity name as typed, sanitized on the way out. The field keeps the user's literal
 *  keystrokes, so only unsalvageable input is an error — see the entity-naming contract. */
export const entityNameField = () =>
  z.string().transform((value) => toValidEntityName(value, value));

/** The message for a name with nothing salvageable in it, or undefined when there is. */
export const unsalvageableNameError = (value: string, label: string): string | undefined => {
  if (sanitizeEntityName(value) !== undefined) return undefined;
  return value ? `${label} must contain at least one letter or number.` : `${label} is required.`;
};

/** Where a name's uniqueness check stands. A debounced value that has fallen behind what is on
 *  screen reads as still checking, never as a verdict for a name the user has moved on from. */
export type NameCheckStatus = 'checking' | 'conflict' | 'failed' | 'available' | undefined;

export const nameCheckStatus = (
  preview: string,
  debounced: string,
  query: { data?: { data?: unknown[] }; isFetching: boolean; isError: boolean }
): NameCheckStatus => {
  if (!preview) return undefined;
  if (debounced !== preview || query.isFetching) return 'checking';
  if (query.isError) return 'failed';
  return (query.data?.data?.length ?? 0) > 0 ? 'conflict' : 'available';
};

/** slotHelp/slotError for a name field, first match wins per the contract's precedence table. */
export const nameFieldSlots = ({
  entity,
  preview,
  status,
  schemaError,
  describe,
}: {
  entity: string;
  preview: string;
  status: NameCheckStatus;
  schemaError?: string;
  describe: string;
}): { slotHelp?: React.ReactNode; slotError?: string; status?: 'error' } => {
  if (status === 'checking') return { slotHelp: 'Checking name...' };
  if (status === 'conflict')
    return { slotError: `An ${entity} named ${preview} already exists`, status: 'error' };
  if (schemaError) return { slotError: schemaError, status: 'error' };
  if (status === 'failed')
    return { slotHelp: "Couldn't check name availability. You can still submit." };
  if (!preview) return { slotHelp: describe };
  return {
    slotHelp: (
      <>
        Your {entity} will be created as <span className="text-primary">{preview}</span>
      </>
    ),
  };
};

/** The server's own explanation for a failed submit, falling back to the transport error.
 *  Without the `detail`, a 422 reads only as "Request failed with status code 422". */
export const submitErrorMessage = (error: unknown): string | undefined => {
  if (!error) return undefined;
  const detail = (error as { response?: { data?: { detail?: unknown } } } | undefined)?.response
    ?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  // Pydantic validation errors arrive as a list of {loc, msg} objects.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown })?.msg)
      .filter((msg): msg is string => typeof msg === 'string' && msg.length > 0);
    if (messages.length) return messages.join('; ');
  }
  return error instanceof Error ? error.message : 'An error occurred';
};
