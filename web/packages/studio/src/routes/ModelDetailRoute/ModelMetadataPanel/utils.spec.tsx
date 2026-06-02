// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FilesetPurpose,
  type FilesetOutput,
  type HuggingfaceStorageConfig,
} from '@nemo/sdk/generated/platform/schema';
import { getMetadataSections } from '@studio/routes/ModelDetailRoute/ModelMetadataPanel/utils';
import { isValidElement } from 'react';

const huggingfaceFileset: FilesetOutput = {
  id: 'model-1',
  name: 'my-model',
  workspace: 'ws',
  description: '',
  purpose: FilesetPurpose.model,
  storage: {
    type: 'huggingface',
    repo_id: 'meta-llama/Llama-2-7b',
  } as HuggingfaceStorageConfig,
  metadata: {},
  custom_fields: {},
  project: '',
  created_at: '',
  updated_at: '',
};

const findRow = (
  sections: ReturnType<typeof getMetadataSections>,
  sectionValue: string,
  rowLabel: string
) =>
  sections
    .find((section) => section.value === sectionValue)
    ?.rows.find((row) => row.label === rowLabel);

describe('getMetadataSections', () => {
  // README frontmatter is user-supplied. `license_link` must be gated against
  // `javascript:` / `data:` so a malicious model card can't inject an
  // executable URL into the rendered <Anchor>.
  describe('license_link safety', () => {
    it('renders license as plain text when license_link uses an unsafe scheme', () => {
      const sections = getMetadataSections(huggingfaceFileset, {
        license: 'MIT',
        license_link: 'javascript:alert(1)',
      });
      const license = findRow(sections, 'details', 'License');
      expect(license?.value).toBe('MIT');
    });

    it('renders license as an anchor when license_link is https', () => {
      const sections = getMetadataSections(huggingfaceFileset, {
        license: 'MIT',
        license_link: 'https://opensource.org/license/mit',
      });
      const license = findRow(sections, 'details', 'License');
      expect(isValidElement(license?.value)).toBe(true);
    });
  });

  it('always includes a Source section with a Storage row', () => {
    const sections = getMetadataSections(huggingfaceFileset, undefined);
    expect(findRow(sections, 'source', 'Storage')?.value).toBe('Hugging Face');
  });

  it('omits the Details section when readme metadata is empty', () => {
    const sections = getMetadataSections(huggingfaceFileset, {});
    expect(sections.find((section) => section.value === 'details')).toBeUndefined();
  });
});
