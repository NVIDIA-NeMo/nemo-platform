// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ENTITY_NAME_MAX_LENGTH, toValidEntityName } from '@nemo/common/src/utils/entityName';

/** Max length (first char + 62) per the entity store pattern. */
export const FILESET_NAME_MAX_LENGTH = ENTITY_NAME_MAX_LENGTH;

const FALLBACK = 'fileset';

/** Rewrite any input into a value that satisfies `ENTITY_NAME_REGEXP`. */
export function toValidFilesetName(input: string): string {
  return toValidEntityName(input, FALLBACK);
}
