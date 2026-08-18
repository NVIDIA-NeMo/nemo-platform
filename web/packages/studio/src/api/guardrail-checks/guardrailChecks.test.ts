// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  resolveConfigModel,
  runGuardrailCheck,
  runGuardrailChecks,
  updateGuardrailCheck,
} from '@studio/api/guardrail-checks/guardrailChecks';
import {
  GUARDRAIL_CHECKS_ENTITY_TYPE,
  type GuardrailCheckEntity,
} from '@studio/api/guardrail-checks/types';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  getMockGuardrailCheck,
  recordedCheckRequests,
  resetGuardrailMocks,
} from '@studio/mocks/handlers/guardrails';
import { server } from '@studio/mocks/node';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'default';
const CONFIG_ID = 'cfg-1';

const CHECK_BY_NAME_URL = `${PLATFORM_BASE_URL}/apis/entities/v2/workspaces/:workspace/entities/${GUARDRAIL_CHECKS_ENTITY_TYPE}/:name`;

beforeEach(() => {
  resetGuardrailMocks();
});

/** The seeded check, as a caller would have snapshotted it from the list query. */
const snapshot = (name: string): GuardrailCheckEntity => {
  const check = getMockGuardrailCheck(name);
  if (!check) throw new Error(`missing fixture: ${name}`);
  return structuredClone(check);
};

describe('resolveConfigModel', () => {
  it('prefers the model marked type "main"', () => {
    const config: RailsConfig = {
      models: [
        { type: 'embeddings', engine: 'openai', model: 'text-embedding-ada-002' },
        { type: 'main', engine: 'openai', model: 'gpt-4' },
      ],
    };
    expect(resolveConfigModel(config, 'pii-filter')).toBe('gpt-4');
  });

  it('falls back to the first model that declares a reference', () => {
    const config: RailsConfig = {
      models: [{ type: 'embeddings', engine: 'openai', model: 'text-embedding-ada-002' }],
    };
    expect(resolveConfigModel(config, 'pii-filter')).toBe('text-embedding-ada-002');
  });

  it.each([
    ['no models', { models: [] } satisfies RailsConfig],
    ['models without a reference', { models: [{ type: 'main', engine: 'openai' }] }],
    ['an absent config', undefined],
  ])('throws a named error for %s', (_label, config) => {
    expect(() => resolveConfigModel(config as RailsConfig | undefined, 'pii-filter')).toThrow(
      "Guardrail config 'pii-filter' has no usable model to run checks against."
    );
  });
});

describe('runGuardrailCheck', () => {
  it('sends the check messages against the parent config model and records the run', async () => {
    const check = snapshot('benign-greeting');

    const { run } = await runGuardrailCheck(WORKSPACE, check);

    expect(recordedCheckRequests).toEqual([
      {
        model: 'gpt-4',
        messages: [{ role: 'user', content: 'Hello there' }],
        guardrails: { config_ids: ['pii-filter'] },
      },
    ]);
    expect(run.status).toBe('success');
    expect(run.config_version).toBe(1);

    const persisted = getMockGuardrailCheck('benign-greeting');
    expect(persisted?.data.runs).toEqual([run]);
    expect(persisted?.db_version).toBe(2);
  });

  it('appends to existing run history rather than replacing it', async () => {
    const { run } = await runGuardrailCheck(WORKSPACE, snapshot('leaks-ssn'));

    const persisted = getMockGuardrailCheck('leaks-ssn');
    expect(persisted?.data.runs).toHaveLength(2);
    expect(persisted?.data.runs.at(-1)).toEqual(run);
    expect(run.status).toBe('blocked');
  });

  // Regression: a concurrent edit bumps db_version between the snapshot and this write-back.
  // /checks already ran, so the record must be re-applied to fresh state, not discarded.
  it('re-reads and retries the write-back when a concurrent edit bumps the version', async () => {
    const stale = snapshot('benign-greeting');

    await updateGuardrailCheck(WORKSPACE, 'benign-greeting', {
      data: { ...stale.data, messages: [{ role: 'user', content: 'edited elsewhere' }] },
      expected_db_version: stale.db_version,
      parent: CONFIG_ID,
    });

    const { run } = await runGuardrailCheck(WORKSPACE, stale);

    const persisted = getMockGuardrailCheck('benign-greeting');
    expect(persisted?.data.runs).toEqual([run]);
    // The concurrent edit survives: the retry re-applied the run onto the fresh entity.
    expect(persisted?.data.messages).toEqual([{ role: 'user', content: 'edited elsewhere' }]);
  });

  it('surfaces a conflict that persists across the retry', async () => {
    server.use(
      http.put(CHECK_BY_NAME_URL, () =>
        HttpResponse.json({ detail: 'still conflicting' }, { status: 409 })
      )
    );

    await expect(runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'))).rejects.toThrow();
  });

  it('rejects a check with no parent config before calling /checks', async () => {
    const orphan: GuardrailCheckEntity = { ...snapshot('benign-greeting'), parent: undefined };

    await expect(runGuardrailCheck(WORKSPACE, orphan)).rejects.toThrow(
      'has no parent config to resolve a model from'
    );
    expect(recordedCheckRequests).toHaveLength(0);
  });

  it('snapshots the saved config coverage onto the run', async () => {
    const { run } = await runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'));

    // cfg-1 declares two input and two output flows, none of which the registry
    // recognizes — so each falls back to its raw name.
    expect(run.activated_guardrails?.map((g) => g.label)).toEqual([
      'check pii',
      'check toxicity',
      'mask pii output',
      'check output facts',
    ]);
    expect(run.is_draft).toBeUndefined();
  });
});

describe('runGuardrailCheck against a draft', () => {
  /** A draft that differs from cfg-1 in both its model and its rails. */
  const DRAFT: RailsConfig = {
    models: [{ type: 'main', engine: 'openai', model: 'gpt-4o-draft' }],
    instructions: [{ type: 'general', content: 'Be extremely cautious.' }],
    rails: { input: { flows: ['jailbreak detection'] } },
  };

  it('sends the draft inline instead of referencing the saved config by id', async () => {
    await runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'), DRAFT);

    expect(recordedCheckRequests).toEqual([
      {
        model: 'gpt-4o-draft',
        messages: [{ role: 'user', content: 'Hello there' }],
        guardrails: { config: DRAFT },
      },
    ]);
    // Never both: the service's validator would silently discard config_ids.
    expect(recordedCheckRequests[0]?.guardrails).not.toHaveProperty('config_ids');
  });

  it('records the run as a draft with no config version', async () => {
    const { run } = await runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'), DRAFT);

    expect(run.is_draft).toBe(true);
    expect(run.config_version).toBeUndefined();
    expect(getMockGuardrailCheck('benign-greeting')?.data.runs).toEqual([run]);
  });

  it("snapshots the draft's coverage, not the saved config's", async () => {
    const { run } = await runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'), DRAFT);

    const labels = run.activated_guardrails?.map((g) => g.label);
    expect(labels).toContain('Jailbreak Detection');
    expect(labels).not.toContain('check pii');
  });

  it("overrides a check's stored guardrails rather than silently ignoring the draft", async () => {
    const check = snapshot('benign-greeting');
    check.data.guardrails = { config_ids: ['some-other-config'] };

    await runGuardrailCheck(WORKSPACE, check, DRAFT);

    expect(recordedCheckRequests[0]?.guardrails).toEqual({ config: DRAFT });
  });

  it('rejects a draft with no usable model before calling /checks', async () => {
    await expect(
      runGuardrailCheck(WORKSPACE, snapshot('benign-greeting'), { models: [] })
    ).rejects.toThrow("Guardrail config 'pii-filter' has no usable model to run checks against.");
    expect(recordedCheckRequests).toHaveLength(0);
  });
});

describe('runGuardrailChecks', () => {
  it('captures per-check failures without rejecting the batch', async () => {
    server.use(
      http.post(`${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/checks`, () =>
        HttpResponse.json({ detail: 'rails unavailable' }, { status: 503 })
      )
    );

    const results = await runGuardrailChecks(WORKSPACE, [
      snapshot('leaks-ssn'),
      snapshot('benign-greeting'),
    ]);

    expect(results).toHaveLength(2);
    expect(results.every((result) => 'error' in result)).toBe(true);
    expect(results.map((result) => result.name)).toEqual(['leaks-ssn', 'benign-greeting']);
  });

  it('reports a mix of successes and failures', async () => {
    const results = await runGuardrailChecks(WORKSPACE, [
      snapshot('benign-greeting'),
      { ...snapshot('leaks-ssn'), parent: undefined },
    ]);

    expect(results[0]).toMatchObject({ name: 'benign-greeting', run: { status: 'success' } });
    expect(results[1]).toHaveProperty('error');
  });
});
