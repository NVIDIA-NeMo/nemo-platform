// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import {
  deriveScopes,
  detectorMeta,
  listConfiguredDetectors,
  summarizeDetector,
} from '@studio/routes/guardrails/GuardrailConfigTab/detectors';

describe('listConfiguredDetectors', () => {
  it('returns configured detectors in canonical (first-party first) order', () => {
    const rails: RailsOutput = {
      config: {
        clavata: { server_endpoint: 'https://example.com' },
        content_safety: { reasoning: { enabled: true } },
        jailbreak_detection: { nim_base_url: 'http://localhost:8000/v1' },
      },
    };
    expect(listConfiguredDetectors(rails)).toEqual([
      'content_safety',
      'jailbreak_detection',
      'clavata',
    ]);
  });

  it('appends unknown detector keys so nothing is dropped', () => {
    const rails = { config: { future_detector: { foo: 'bar' } } } as unknown as RailsOutput;
    expect(listConfiguredDetectors(rails)).toEqual(['future_detector']);
  });

  it('returns an empty list when no config is present', () => {
    expect(listConfiguredDetectors(undefined)).toEqual([]);
    expect(listConfiguredDetectors({})).toEqual([]);
  });
});

describe('deriveScopes', () => {
  it('derives scope from the detector own input/output sub-config', () => {
    const rails: RailsOutput = {
      config: { gliner: { input: { entities: ['email'] }, output: { entities: ['ssn'] } } },
    };
    expect(deriveScopes(rails, 'gliner')).toEqual(['input', 'output']);
  });

  it('derives scope from flows that reference the detector', () => {
    const rails: RailsOutput = {
      config: { content_safety: { reasoning: { enabled: true } } },
      input: { flows: ['content safety check input $model=content_safety'] },
      output: { flows: ['content safety check output $model=content_safety'] },
    };
    expect(deriveScopes(rails, 'content_safety')).toEqual(['input', 'output']);
  });

  it('unions both signals and orders scopes canonically', () => {
    const rails: RailsOutput = {
      config: { sensitive_data_detection: { output: { entities: ['PERSON'] } } },
      input: { flows: ['mask sensitive data on input'] },
    };
    expect(deriveScopes(rails, 'sensitive_data_detection')).toEqual(['input', 'output']);
  });
});

describe('detectorMeta', () => {
  it('returns known metadata and humanizes unknown keys', () => {
    expect(detectorMeta('content_safety')).toEqual({ label: 'Content Safety', firstParty: true });
    expect(detectorMeta('some_new_thing')).toEqual({ label: 'Some New Thing', firstParty: false });
  });
});

describe('summarizeDetector', () => {
  it('summarizes scalars, scoped entities, toggles, and masks secrets', () => {
    const fields = summarizeDetector({
      nim_base_url: 'http://localhost:8000/v1',
      api_key: 'super-secret',
      reasoning: { enabled: false },
      input: { entities: ['EMAIL', 'PHONE'] },
    });
    expect(fields).toContainEqual({ label: 'Nim Base Url', value: 'http://localhost:8000/v1' });
    expect(fields).toContainEqual({ label: 'Api Key', value: '••••••••' });
    expect(fields).toContainEqual({ label: 'Reasoning', value: 'Disabled' });
    expect(fields).toContainEqual({ label: 'Input entities', value: 'EMAIL, PHONE' });
  });

  it('masks prefixed and suffixed secret keys', () => {
    const fields = summarizeDetector({
      nim_api_key: 'nvapi-xxx',
      hf_token: 'hf_xxx',
      access_token: 'tok-xxx',
      private_key: 'pk-xxx',
    });
    expect(fields).toContainEqual({ label: 'Nim Api Key', value: '••••••••' });
    expect(fields).toContainEqual({ label: 'Hf Token', value: '••••••••' });
    expect(fields).toContainEqual({ label: 'Access Token', value: '••••••••' });
    expect(fields).toContainEqual({ label: 'Private Key', value: '••••••••' });
  });

  it('does not mask non-secret keys that merely contain a secret word', () => {
    const fields = summarizeDetector({
      max_tokens: 512,
      nim_base_url: 'http://localhost:8000/v1',
    });
    expect(fields).toContainEqual({ label: 'Max Tokens', value: '512' });
    expect(fields).toContainEqual({ label: 'Nim Base Url', value: 'http://localhost:8000/v1' });
  });

  it('returns no fields for non-object input', () => {
    expect(summarizeDetector(undefined)).toEqual([]);
    expect(summarizeDetector('nope')).toEqual([]);
  });
});
