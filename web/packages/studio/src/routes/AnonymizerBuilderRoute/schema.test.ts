// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DETECTION_ROLES,
  REPLACE_ROLE,
  REWRITE_ROLES,
  ROLE_LABELS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import {
  AnonymizerFormData,
  buildAnonymizerJobRequest,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';

const ALL_ROLES = [...DETECTION_ROLES, REPLACE_ROLE, ...REWRITE_ROLES];

const roleModels = (model: string, provider: string): AnonymizerFormData['roleModels'] =>
  Object.fromEntries(ALL_ROLES.map((role) => [role, { modelId: role, model, provider }]));

const form = (overrides: Partial<AnonymizerFormData> = {}): AnonymizerFormData => ({
  ...getAnonymizerFormDefaults(),
  source: 'https://example.com/data.csv',
  roleModels: roleModels('openai/gpt-oss-120b', 'default/nvidia'),
  ...overrides,
});

describe('buildAnonymizerJobRequest', () => {
  it('tags each replace strategy with its kind', () => {
    for (const strategy of ['substitute', 'redact', 'annotate', 'hash'] as const) {
      const req = buildAnonymizerJobRequest(form({ strategy }));
      expect((req.spec.config.replace as { kind: string }).kind).toBe(strategy);
    }
  });

  it('substitute sends only the kind', () => {
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute' }));
    expect(req.spec.config).toEqual({ replace: { kind: 'substitute' } });
  });

  it('carries strategy params for redact and hash, omitting empty templates', () => {
    const redact = buildAnonymizerJobRequest(
      form({ strategy: 'redact', redactTemplate: '  <{label}>  ', redactNormalizeLabel: false })
    );
    expect(redact.spec.config.replace).toEqual({
      kind: 'redact',
      normalize_label: false,
      format_template: '<{label}>',
    });

    const hash = buildAnonymizerJobRequest(
      form({ strategy: 'hash', hashAlgorithm: 'sha1', hashDigestLength: 12, hashTemplate: '' })
    );
    expect(hash.spec.config.replace).toEqual({
      kind: 'hash',
      algorithm: 'sha1',
      digest_length: 12,
    });
  });

  it('routes rewrite to config.rewrite with the library defaults', () => {
    const req = buildAnonymizerJobRequest(form({ strategy: 'rewrite' }));
    expect(req.spec.config).toEqual({
      rewrite: {
        risk_tolerance: 'low',
        max_repair_iterations: 3,
        strict_entity_protection: false,
      },
    });
  });

  it('sends privacy_goal only in custom mode, trimming both fields', () => {
    const custom = buildAnonymizerJobRequest(
      form({
        strategy: 'rewrite',
        privacyGoalMode: 'custom',
        privacyProtect: '  patient identifiers  ',
        privacyPreserve: '  clinical findings  ',
      })
    );
    expect(custom.spec.config.rewrite?.privacy_goal).toEqual({
      protect: 'patient identifiers',
      preserve: 'clinical findings',
    });

    const defaults = buildAnonymizerJobRequest(
      form({ strategy: 'rewrite', privacyGoalMode: 'default', privacyProtect: 'ignored' })
    );
    expect(defaults.spec.config.rewrite?.privacy_goal).toBeUndefined();
  });

  it('omits blank rewrite instructions and carries the tuned params', () => {
    const blank = buildAnonymizerJobRequest(
      form({ strategy: 'rewrite', rewriteInstructions: '   ' })
    );
    expect(blank.spec.config.rewrite?.instructions).toBeUndefined();

    const tuned = buildAnonymizerJobRequest(
      form({
        strategy: 'rewrite',
        rewriteInstructions: '  keep the tone  ',
        riskTolerance: 'minimal',
        maxRepairRounds: 0,
        strictEntityProtection: true,
      })
    );
    expect(tuned.spec.config.rewrite).toEqual({
      instructions: 'keep the tone',
      risk_tolerance: 'minimal',
      max_repair_iterations: 0,
      strict_entity_protection: true,
    });
  });

  it('drops rewrite params when a replace strategy is selected', () => {
    const req = buildAnonymizerJobRequest(
      form({ strategy: 'redact', privacyGoalMode: 'custom', privacyProtect: 'names' })
    );
    expect(req.spec.config.rewrite).toBeUndefined();
  });

  it('trims the source and omits empty optional fields', () => {
    const req = buildAnonymizerJobRequest(
      form({ source: '  s3://x.csv  ', textColumn: '', dataSummary: '   ' })
    );
    expect(req.spec.data.source).toBe('s3://x.csv');
    expect(req.spec.data.text_column).toBeUndefined();
    expect(req.spec.data.data_summary).toBeUndefined();
  });

  it('deduplicates identical role models into a single model_config with a default timeout', () => {
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute' }));
    expect(req.spec.model_configs).toEqual([
      {
        alias: 'model-1',
        model: 'openai/gpt-oss-120b',
        provider: 'default/nvidia',
        inference_parameters: { timeout: 500, max_tokens: 16384 },
      },
    ]);
  });

  it('emits one model_config per unique model+provider', () => {
    const models = roleModels('openai/gpt-oss-120b', 'default/nvidia');
    models[DETECTION_ROLES[0]] = {
      modelId: 'gliner',
      model: 'nvidia/gliner-pii',
      provider: 'default/nvidia',
    };
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute', roleModels: models }));
    expect(req.spec.model_configs).toHaveLength(2);
    expect(req.spec.selected_models?.detection?.[DETECTION_ROLES[0]]).not.toBe(
      req.spec.selected_models?.replace?.[REPLACE_ROLE]
    );
  });

  it('maps detection + replace roles for substitute, detection + rewrite for rewrite', () => {
    const sub = buildAnonymizerJobRequest(form({ strategy: 'substitute' })).spec.selected_models;
    expect(sub?.detection?.entity_detector).toBe('model-1');
    expect(sub?.replace?.replacement_generator).toBe('model-1');
    expect(sub?.rewrite).toBeUndefined();

    const rew = buildAnonymizerJobRequest(form({ strategy: 'rewrite' })).spec.selected_models;
    expect(rew?.detection?.entity_detector).toBe('model-1');
    expect(rew?.rewrite?.rewriter).toBe('model-1');
  });

  it('maps the replacement generator for rewrite so the backend alias check passes', () => {
    const rew = buildAnonymizerJobRequest(form({ strategy: 'rewrite' })).spec.selected_models;
    expect(rew?.replace?.[REPLACE_ROLE]).toBe('model-1');
  });

  it('maps only detection roles for redact/annotate/hash', () => {
    for (const strategy of ['redact', 'annotate', 'hash'] as const) {
      const selected = buildAnonymizerJobRequest(form({ strategy })).spec.selected_models;
      expect(selected?.detection?.entity_detector).toBe('model-1');
      expect(selected?.replace).toBeUndefined();
      expect(selected?.rewrite).toBeUndefined();
    }
  });

  it('exposes a label for every configurable role', () => {
    for (const role of ALL_ROLES) {
      expect(ROLE_LABELS[role]).toBeTruthy();
    }
  });

  it('sets config.detect.entity_labels only for custom labels without defaults', () => {
    const custom = buildAnonymizerJobRequest(
      form({ entityMode: 'custom', includeDefaultEntities: false, entityLabels: ['email', 'ssn'] })
    );
    expect(custom.spec.config.detect).toEqual({ entity_labels: ['email', 'ssn'] });

    const withDefaults = buildAnonymizerJobRequest(
      form({ entityMode: 'custom', includeDefaultEntities: true, entityLabels: ['email'] })
    );
    expect(withDefaults.spec.config.detect).toBeUndefined();

    const auto = buildAnonymizerJobRequest(form({ entityMode: 'auto', entityLabels: ['email'] }));
    expect(auto.spec.config.detect).toBeUndefined();
  });

  it('attaches inference_parameters and splits configs when params differ', () => {
    const models = roleModels('openai/gpt-oss-120b', 'default/nvidia');
    models[DETECTION_ROLES[0]] = {
      modelId: 'gpt',
      model: 'openai/gpt-oss-120b',
      provider: 'default/nvidia',
      params: { temperature: 0.1 },
    };
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute', roleModels: models }));
    expect(req.spec.model_configs).toHaveLength(2);
    const withTemp = req.spec.model_configs?.find(
      (c) => (c.inference_parameters as { temperature?: number })?.temperature != null
    );
    expect(withTemp?.inference_parameters).toEqual({
      timeout: 500,
      max_tokens: 16384,
      temperature: 0.1,
    });
  });
});
