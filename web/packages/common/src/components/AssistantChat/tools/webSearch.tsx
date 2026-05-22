// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartProps } from '@assistant-ui/react';
import { ToolCallShell } from '@nemo/common/src/components/AssistantChat/parts/ToolCallShell';
import type { StudioTool } from '@nemo/common/src/components/AssistantChat/tools/types';
import { Banner, Text } from '@nvidia/foundations-react-core';
import { Globe, Search } from 'lucide-react';

interface WebSearchArgs {
  readonly query?: string;
  readonly max_results?: number;
}

interface WebSearchResultItem {
  readonly title: string;
  readonly url: string;
  readonly snippet?: string;
}

interface WebSearchResult {
  readonly query: string;
  readonly results: readonly WebSearchResultItem[];
  readonly note?: string;
}

const parseArgs = (args: unknown, argsText: string | undefined): WebSearchArgs => {
  if (args && typeof args === 'object') return args as WebSearchArgs;
  if (!argsText) return {};
  try {
    return JSON.parse(argsText) as WebSearchArgs;
  } catch {
    return {};
  }
};

const isWebSearchResult = (value: unknown): value is WebSearchResult =>
  typeof value === 'object' &&
  value !== null &&
  'results' in value &&
  Array.isArray((value as WebSearchResult).results);

const WebSearchPart = (props: ToolCallMessagePartProps) => {
  const { query } = parseArgs(props.args, props.argsText);
  const isStreaming = props.status.type === 'running';
  const result = isWebSearchResult(props.result) ? props.result : null;
  const errorText =
    props.isError && typeof props.result === 'string'
      ? props.result
      : props.isError && props.result && typeof props.result === 'object' && 'error' in props.result
        ? String((props.result as { error: unknown }).error)
        : null;

  return (
    <ToolCallShell
      icon={<Search size={14} aria-hidden />}
      label="Web search"
      toolName={props.toolName}
      status={props.status}
      summaryRight={
        query ? (
          <Text kind="body/regular/sm" className="truncate text-fg-muted">
            “{query}”
          </Text>
        ) : null
      }
      defaultOpen
    >
      <div className="flex flex-col gap-density-sm px-density-sm pb-density-sm">
        {isStreaming && !result ? (
          <Text kind="body/regular/sm" className="text-fg-muted">
            Searching…
          </Text>
        ) : null}
        {errorText ? (
          <Banner kind="inline" status="warning">
            {errorText}
          </Banner>
        ) : null}
        {result?.note ? (
          <Banner kind="inline" status="info">
            {result.note}
          </Banner>
        ) : null}
        {result?.results?.length ? (
          <ul className="flex flex-col gap-density-sm">
            {result.results.map((item) => (
              <li
                key={item.url}
                className="flex flex-col gap-density-xs rounded border border-base bg-surface-base p-density-sm"
              >
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-density-xs text-sm font-medium text-fg-link hover:underline"
                >
                  <Globe size={12} aria-hidden />
                  <span className="truncate">{item.title || item.url}</span>
                </a>
                <Text kind="body/regular/sm" className="truncate text-fg-muted">
                  {item.url}
                </Text>
                {item.snippet ? (
                  <Text kind="body/regular/sm" className="line-clamp-3">
                    {item.snippet}
                  </Text>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </ToolCallShell>
  );
};

const WEB_SEARCH_BACKEND_HEADER = 'X-Nemo-Web-Search-Provider';

export interface WebSearchProvider {
  readonly search: (
    args: { query: string; maxResults: number },
    ctx: { signal: AbortSignal }
  ) => Promise<WebSearchResult>;
}

const stubProvider: WebSearchProvider = {
  search: async ({ query }) => ({
    query,
    results: [],
    note:
      'Web search backend is not configured in this build. The frontend tool is wired ' +
      'end-to-end; once a Playwright-backed `/web-search` endpoint is available, swap the ' +
      'default provider for one that calls it.',
  }),
};

let activeProvider: WebSearchProvider = stubProvider;

export const setWebSearchProvider = (provider: WebSearchProvider | null): void => {
  activeProvider = provider ?? stubProvider;
};

export const webSearchTool: StudioTool<WebSearchArgs> = {
  name: 'web_search',
  label: 'Web search',
  description:
    'Search the public web (DuckDuckGo via a headless browser, backend-driven). ' +
    'Returns a list of result objects with title, url, and snippet for the model to read. ' +
    'Use for time-sensitive facts, citations, or anything not present in your training data.',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description:
          'Plain-language search query. Avoid quoting unless an exact phrase match matters.',
      },
      max_results: {
        type: 'number',
        description: 'Maximum number of results to return. Defaults to 5, capped at 10.',
      },
    },
    required: ['query'],
    additionalProperties: false,
  },
  execute: async (args, { signal }) => {
    const query = (args?.query ?? '').trim();
    if (!query) return { ok: false, error: 'Missing required `query` argument.' };
    const maxResults = Math.min(10, Math.max(1, args?.max_results ?? 5));
    try {
      const result = await activeProvider.search({ query, maxResults }, { signal });
      return { ok: true, result };
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Web search failed.';
      return { ok: false, error: message };
    }
  },
  Render: WebSearchPart,
};

export const __webSearchInternals = { WEB_SEARCH_BACKEND_HEADER, stubProvider };
