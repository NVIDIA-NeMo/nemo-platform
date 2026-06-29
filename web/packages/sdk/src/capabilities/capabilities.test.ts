// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { toAnthropicTools } from './adapters/anthropic';
import { callMcpTool, toMcpTools } from './adapters/mcp';
import { toOpenAITools } from './adapters/openai';
import { createGateway } from './gateway';
import { invokeCapability } from './invoke';
import { searchCapabilities } from './registry';
import type { CapabilityContext, CapabilityMeta, FetchRequest } from './types';

const listModels: CapabilityMeta = {
  name: 'models_list',
  service: 'platform',
  method: 'GET',
  path: '/apis/models/v2/workspaces/{workspace}/models',
  summary: 'List models',
  description: 'List all model entities in a workspace.',
  tags: ['Models'],
  readOnly: true,
  pathParams: ['workspace'],
  queryParams: ['page', 'page_size'],
  hasBody: false,
  bodyRequired: false,
  inputSchema: {
    type: 'object',
    properties: {
      workspace: { type: 'string' },
      page: { type: 'integer' },
      page_size: { type: 'integer' },
    },
    required: ['workspace'],
  },
};

const createModel: CapabilityMeta = {
  name: 'models_create',
  service: 'platform',
  method: 'POST',
  path: '/apis/models/v2/workspaces/{workspace}/models',
  summary: 'Create model',
  description: 'Create a new model entity.',
  tags: ['Models'],
  readOnly: false,
  pathParams: ['workspace'],
  queryParams: [],
  hasBody: true,
  bodyRequired: true,
  inputSchema: {
    type: 'object',
    properties: { workspace: { type: 'string' }, body: { type: 'object' } },
    required: ['workspace', 'body'],
  },
};

const registry: CapabilityMeta[] = [listModels, createModel];

const makeContext = (
  impl?: (req: FetchRequest) => unknown
): {
  ctx: CapabilityContext;
  calls: FetchRequest[];
} => {
  const calls: FetchRequest[] = [];
  const fetcher = vi.fn(async (req: FetchRequest) => {
    calls.push(req);
    return impl ? impl(req) : { ok: true };
  });
  return {
    ctx: { fetchers: { platform: fetcher as never }, workspace: 'default' },
    calls,
  };
};

describe('invokeCapability', () => {
  it('substitutes path params, splits query params, and omits body for GET', async () => {
    const { ctx, calls } = makeContext();
    await invokeCapability(listModels, { workspace: 'ws1', page: 2 }, ctx);
    expect(calls[0]).toMatchObject({
      url: '/apis/models/v2/workspaces/ws1/models',
      method: 'GET',
      params: { page: 2 },
    });
    expect(calls[0].data).toBeUndefined();
  });

  it('falls back to ctx.workspace when the workspace path param is omitted', async () => {
    const { ctx, calls } = makeContext();
    await invokeCapability(listModels, { page: 1 }, ctx);
    expect(calls[0].url).toBe('/apis/models/v2/workspaces/default/models');
  });

  it('sends the body for write operations', async () => {
    const { ctx, calls } = makeContext();
    await invokeCapability(createModel, { workspace: 'ws1', body: { name: 'm' } }, ctx);
    expect(calls[0]).toMatchObject({ method: 'POST', data: { name: 'm' } });
  });

  it('throws when a required path param is missing and no fallback exists', async () => {
    const fetcher = vi.fn(async () => ({}));
    const ctx: CapabilityContext = { fetchers: { platform: fetcher as never } };
    await expect(invokeCapability(createModel, { body: {} }, ctx)).rejects.toThrow(
      /Missing required path parameter "workspace"/
    );
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('throws when no fetcher is registered for the service', async () => {
    await expect(
      invokeCapability(listModels, { workspace: 'ws1' }, { fetchers: {} })
    ).rejects.toThrow(/No fetcher registered for service "platform"/);
  });
});

describe('searchCapabilities', () => {
  it('finds operations by keyword and ranks name/path hits first', () => {
    const results = searchCapabilities(registry, 'models');
    expect(results.map((r) => r.name)).toContain('models_list');
    expect(results.map((r) => r.name)).toContain('models_create');
  });

  it('filters by readOnly', () => {
    const results = searchCapabilities(registry, 'models', { readOnly: false });
    expect(results.map((r) => r.name)).toEqual(['models_create']);
  });

  it('returns nothing when not every term matches', () => {
    expect(searchCapabilities(registry, 'models nonexistentterm')).toHaveLength(0);
  });

  it('caps results at a positive integer limit', () => {
    expect(searchCapabilities(registry, 'models', { limit: 1 })).toHaveLength(1);
  });

  it('ignores non-positive or non-integer limits instead of dropping results', () => {
    const all = searchCapabilities(registry, 'models');
    for (const limit of [0, -1, 1.5, NaN]) {
      expect(searchCapabilities(registry, 'models', { limit })).toHaveLength(all.length);
    }
  });
});

describe('gateway', () => {
  const gateway = createGateway(registry);
  const get = (name: string) => gateway.find((c) => c.name === name)!;

  it('exposes exactly the four gateway tools with correct confirmation flags', () => {
    expect(gateway.map((c) => c.name)).toEqual([
      'search_capabilities',
      'describe_capability',
      'read_capability',
      'run_capability',
    ]);
    expect(get('run_capability').requiresConfirmation).toBe(true);
    expect(get('read_capability').requiresConfirmation).toBe(false);
  });

  it('search_capabilities returns matching operations', async () => {
    const { ctx } = makeContext();
    const res = await get('search_capabilities').execute({ query: 'models' }, ctx);
    const payload = JSON.parse(res.content) as { count: number };
    expect(payload.count).toBe(2);
  });

  it('describe_capability returns the input schema', async () => {
    const { ctx } = makeContext();
    const res = await get('describe_capability').execute({ name: 'models_create' }, ctx);
    const payload = JSON.parse(res.content) as { method: string; inputSchema: unknown };
    expect(payload.method).toBe('POST');
    expect(payload.inputSchema).toEqual(createModel.inputSchema);
  });

  it('read_capability invokes a GET and returns its result', async () => {
    const { ctx, calls } = makeContext(() => ({ data: [{ id: '1' }] }));
    const res = await get('read_capability').execute(
      { name: 'models_list', args: { workspace: 'ws1' } },
      ctx
    );
    expect(calls[0].method).toBe('GET');
    expect(JSON.parse(res.content)).toEqual({ data: [{ id: '1' }] });
  });

  it('read_capability refuses a mutating operation', async () => {
    const { ctx, calls } = makeContext();
    const res = await get('read_capability').execute({ name: 'models_create' }, ctx);
    expect(res.isError).toBe(true);
    expect(res.content).toMatch(/Use run_capability/);
    expect(calls).toHaveLength(0);
  });

  it('run_capability refuses a read-only operation', async () => {
    const { ctx } = makeContext();
    const res = await get('run_capability').execute({ name: 'models_list' }, ctx);
    expect(res.isError).toBe(true);
    expect(res.content).toMatch(/Use read_capability/);
  });

  it('run_capability executes a write and surfaces fetcher errors', async () => {
    const { ctx } = makeContext(() => {
      throw new Error('boom');
    });
    const res = await get('run_capability').execute(
      { name: 'models_create', args: { workspace: 'ws1', body: {} } },
      ctx
    );
    expect(res.isError).toBe(true);
    expect(res.content).toMatch(/models_create failed: boom/);
  });

  it('reports unknown operations', async () => {
    const { ctx } = makeContext();
    const res = await get('describe_capability').execute({ name: 'nope' }, ctx);
    expect(res.isError).toBe(true);
    expect(res.content).toMatch(/Unknown operation/);
  });
});

describe('adapters', () => {
  const gateway = createGateway(registry);

  it('toAnthropicTools maps name/description/input_schema', () => {
    const tools = toAnthropicTools(gateway);
    expect(tools[0]).toMatchObject({ name: 'search_capabilities' });
    expect(tools[0].input_schema).toBeDefined();
  });

  it('toOpenAITools wraps in the function shape', () => {
    const tools = toOpenAITools(gateway);
    expect(tools[0].type).toBe('function');
    expect(tools[0].function.name).toBe('search_capabilities');
    expect(tools[0].function.parameters).toBeDefined();
  });

  it('toMcpTools and callMcpTool dispatch by name', async () => {
    const tools = toMcpTools(gateway);
    expect(tools.map((t) => t.name)).toContain('describe_capability');

    const { ctx } = makeContext();
    const result = await callMcpTool(gateway, ctx, 'search_capabilities', { query: 'models' });
    expect(result.content[0].type).toBe('text');
    expect(result.isError).toBeFalsy();

    const unknown = await callMcpTool(gateway, ctx, 'does_not_exist', {});
    expect(unknown.isError).toBe(true);
  });
});
