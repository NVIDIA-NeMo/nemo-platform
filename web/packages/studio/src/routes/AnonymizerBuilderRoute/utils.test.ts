// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerModelOption } from '@studio/components/NewDataDesignerJobForm/utils';
import { isGlinerModel } from '@studio/routes/AnonymizerBuilderRoute/utils';

const model = (name: string, servedModelName: string, id = name): DataDesignerModelOption =>
  ({ id, name, served_model_name: servedModelName }) as DataDesignerModelOption;

describe('isGlinerModel', () => {
  it('matches on either identifier, regardless of case', () => {
    expect(isGlinerModel(model('nvidia-gliner-pii', 'nvidia/gliner-PII'))).toBe(true);
    expect(isGlinerModel(model('pii-detector', 'nvidia/GLiNER-pii'))).toBe(true);
    expect(isGlinerModel(model('nvidia-gliner-pii', ''))).toBe(true);
  });

  it('ignores the entity id, whose first segment is the workspace', () => {
    expect(
      isGlinerModel(model('pii-detector', 'nvidia/nemotron', 'gliner-team/pii-detector'))
    ).toBe(false);
  });

  it('does not match general chat models', () => {
    expect(isGlinerModel(model('nemotron-3-nano-30b-a3b', 'nvidia/nemotron-3-nano-30b-a3b'))).toBe(
      false
    );
    expect(isGlinerModel(model('gpt-oss-120b', 'openai/gpt-oss-120b'))).toBe(false);
  });
});
