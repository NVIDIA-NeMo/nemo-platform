// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ENTITY_CATEGORIES,
  ENTITY_CATEGORY_OTHER,
} from '@studio/routes/AnonymizerBuilderRoute/constants';

export interface EntitySection {
  readonly heading: string;
  readonly items: string[];
}

/** Group the flat label list from the API under the curated categories, in category order. */
export const buildEntitySections = (available: string[]): EntitySection[] => {
  const remaining = new Set(available);
  const sections: EntitySection[] = [];

  for (const category of ENTITY_CATEGORIES) {
    const items = category.labels.filter((label) => remaining.delete(label));
    if (items.length) sections.push({ heading: category.label, items });
  }

  if (remaining.size) {
    sections.push({ heading: ENTITY_CATEGORY_OTHER, items: [...remaining] });
  }

  return sections;
};

/**
 * The typed value, when it isn't already offered or selected. Surfacing it as an item is what
 * lets a custom label be added, since the underlying combobox has no create affordance.
 */
export const customLabelCandidate = (
  input: string,
  available: string[],
  selected: string[]
): string | null => {
  const candidate = input.trim();
  if (!candidate) return null;
  if (available.includes(candidate) || selected.includes(candidate)) return null;
  return candidate;
};
