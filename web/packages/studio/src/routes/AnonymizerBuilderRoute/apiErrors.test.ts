// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parseAnonymizerApiError } from '@studio/routes/AnonymizerBuilderRoute/apiErrors';

const apiError = (detail: unknown) => ({ response: { data: { detail } } });
const replaceLoc = (kind: string, field: string) => [
  'body',
  'spec',
  'config',
  'replace',
  kind,
  field,
];

describe('parseAnonymizerApiError', () => {
  it('maps replace-template errors to the matching strategy field', () => {
    const { fieldErrors } = parseAnonymizerApiError(
      apiError([{ loc: replaceLoc('annotate', 'format_template'), msg: 'missing text' }])
    );
    expect(fieldErrors).toEqual([{ field: 'annotateTemplate', message: 'missing text' }]);
  });

  it('maps hash params and data fields', () => {
    const { fieldErrors } = parseAnonymizerApiError(
      apiError([
        { loc: replaceLoc('hash', 'digest_length'), msg: 'a' },
        { loc: ['body', 'spec', 'data', 'source'], msg: 'b' },
      ])
    );
    expect(fieldErrors.map((f) => f.field)).toEqual(['hashDigestLength', 'source']);
  });

  it('maps rewrite params, including nested privacy goal fields', () => {
    const rewriteLoc = (...tail: string[]) => ['body', 'spec', 'config', 'rewrite', ...tail];
    const { fieldErrors } = parseAnonymizerApiError(
      apiError([
        { loc: rewriteLoc('privacy_goal', 'protect'), msg: 'too short' },
        { loc: rewriteLoc('privacy_goal', 'preserve'), msg: 'too short' },
        { loc: rewriteLoc('max_repair_iterations'), msg: 'negative' },
        { loc: rewriteLoc('risk_tolerance'), msg: 'bad preset' },
      ])
    );
    expect(fieldErrors.map((f) => f.field)).toEqual([
      'privacyProtect',
      'privacyPreserve',
      'maxRepairRounds',
      'riskTolerance',
    ]);
  });

  it('collects unmapped errors as general messages', () => {
    const { fieldErrors, generalMessages } = parseAnonymizerApiError(
      apiError([{ loc: ['body', 'spec', 'model_configs', 0, 'provider'], msg: 'bad provider' }])
    );
    expect(fieldErrors).toEqual([]);
    expect(generalMessages).toEqual(['bad provider']);
  });

  it('returns empty for non-validation errors', () => {
    expect(parseAnonymizerApiError(new Error('network'))).toEqual({
      fieldErrors: [],
      generalMessages: [],
    });
  });
});
