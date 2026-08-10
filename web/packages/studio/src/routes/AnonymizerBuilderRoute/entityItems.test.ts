// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ENTITY_CATEGORIES,
  ENTITY_CATEGORY_OTHER,
  ENTITY_CUSTOM_TAG_COLOR,
  entityTagColor,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import {
  buildEntitySections,
  customLabelCandidate,
} from '@studio/routes/AnonymizerBuilderRoute/entityItems';

const ALL_CATEGORY_LABELS = ENTITY_CATEGORIES.flatMap((category) => [...category.labels]);

describe('entity categories', () => {
  it('never lists the same label under two categories', () => {
    expect(new Set(ALL_CATEGORY_LABELS).size).toBe(ALL_CATEGORY_LABELS.length);
  });

  it('colours labels by category and falls back for custom ones', () => {
    expect(entityTagColor('first_name')).toBe(ENTITY_CATEGORIES[0].color);
    expect(entityTagColor('ice_cream_flavor')).toBe(ENTITY_CUSTOM_TAG_COLOR);
  });
});

describe('buildEntitySections', () => {
  it('groups labels in category order and drops empty categories', () => {
    const sections = buildEntitySections(['city', 'first_name', 'email']);
    expect(sections).toEqual([
      { heading: 'Personal Identity', items: ['first_name'] },
      { heading: 'Contact & Communication', items: ['email'] },
      { heading: 'Location & Address', items: ['city'] },
    ]);
  });

  it('collects labels missing from the curated map under Other', () => {
    const sections = buildEntitySections(['first_name', 'brand_new_label']);
    expect(sections.at(-1)).toEqual({
      heading: ENTITY_CATEGORY_OTHER,
      items: ['brand_new_label'],
    });
  });

  it('covers every curated label without an Other bucket', () => {
    const sections = buildEntitySections(ALL_CATEGORY_LABELS);
    expect(sections.map((s) => s.heading)).not.toContain(ENTITY_CATEGORY_OTHER);
    expect(sections.flatMap((s) => s.items)).toHaveLength(ALL_CATEGORY_LABELS.length);
  });
});

describe('customLabelCandidate', () => {
  it('offers a trimmed candidate that is neither available nor already selected', () => {
    expect(customLabelCandidate('  foobar ', ['email'], [])).toBe('foobar');
    expect(customLabelCandidate('email', ['email'], [])).toBeNull();
    expect(customLabelCandidate('foobar', [], ['foobar'])).toBeNull();
    expect(customLabelCandidate('   ', [], [])).toBeNull();
  });
});
