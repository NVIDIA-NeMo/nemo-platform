// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { mockSpanById, mockSpansPage, mockTraceById } from '@studio/mocks/intake/telemetry';
import { server } from '@studio/mocks/node';
import { IntakeTraceDetailRoute } from '@studio/routes/IntakeTraceDetailRoute';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';

const LocationSearchProbe = () => {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
};

const renderTraceDetail = (traceId: string, search = '') =>
  renderRoute(undefined, {
    history: `/workspaces/default/intake/traces/${traceId}${search}`,
    routes: [
      {
        path: '/workspaces/:workspace/intake/traces/:traceId',
        element: (
          <>
            <LocationSearchProbe />
            <IntakeTraceDetailRoute />
          </>
        ),
      },
    ],
  });

describe('IntakeTraceDetailRoute', () => {
  it('loads span summaries before fetching detailed span data on selection', async () => {
    const user = userEvent.setup();
    const traceModes: Array<string | null> = [];
    const spanListModes: Array<string | null> = [];
    const detailSpanIds: string[] = [];

    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/traces/:traceId', ({ params, request }) => {
        traceModes.push(new URL(request.url).searchParams.get('mode'));
        const trace = mockTraceById(String(params['traceId']));
        return trace ? HttpResponse.json(trace) : new HttpResponse(null, { status: 404 });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        const url = new URL(request.url);
        spanListModes.push(url.searchParams.get('mode'));
        const traceId = url.searchParams.get('filter[trace_id]');
        const data = traceId
          ? mockSpansPage.data.filter((span) => span.trace_id === traceId)
          : mockSpansPage.data;

        return HttpResponse.json({
          ...mockSpansPage,
          data,
          pagination: {
            ...mockSpansPage.pagination,
            current_page_size: data.length,
            total_results: data.length,
            total_pages: data.length > 0 ? 1 : 0,
          },
          filter: traceId ? { trace_id: traceId } : undefined,
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', async ({ params }) => {
        const spanId = String(params['spanId']);
        await delay(100);
        detailSpanIds.push(spanId);
        const span = mockSpanById(spanId);
        return span ? HttpResponse.json(span) : new HttpResponse(null, { status: 404 });
      })
    );

    renderTraceDetail('trace-agent-run-001');

    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
    expect(await screen.findByText('Generate final response')).toBeInTheDocument();
    expect(await screen.findByLabelText('Loading span details')).toBeInTheDocument();

    await waitFor(() => expect(traceModes).toContain('detailed'));
    await waitFor(() => expect(spanListModes).toContain('summary'));
    expect(traceModes).not.toContain('summary');
    expect(spanListModes).not.toContain('detailed');
    await waitFor(() => expect(detailSpanIds).toContain('span-root-001'));
    expect(detailSpanIds).not.toContain('span-llm-001');
    await waitFor(() =>
      expect(screen.getByTestId('location-search')).toHaveTextContent('spanId=span-root-001')
    );

    await user.click(screen.getByText('Generate final response'));

    await waitFor(() => expect(detailSpanIds).toContain('span-llm-001'));
    await waitFor(() =>
      expect(screen.getByTestId('location-search')).toHaveTextContent('spanId=span-llm-001')
    );
  });

  it('restores the selected span from the spanId query parameter', async () => {
    const detailSpanIds: string[] = [];

    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', ({ params }) => {
        const spanId = String(params['spanId']);
        detailSpanIds.push(spanId);
        const span = mockSpanById(spanId);
        return span ? HttpResponse.json(span) : new HttpResponse(null, { status: 404 });
      })
    );

    renderTraceDetail('trace-agent-run-001', '?spanId=span-llm-001');

    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
    expect((await screen.findAllByText('Generate final response')).length).toBeGreaterThan(0);

    await waitFor(() => expect(detailSpanIds).toContain('span-llm-001'));
    expect(detailSpanIds).not.toContain('span-root-001');
    expect(screen.getByTestId('location-search')).toHaveTextContent('spanId=span-llm-001');
  });

  it('preserves a linked span outside the loaded summary page', async () => {
    const user = userEvent.setup();
    const detailSpanIds: string[] = [];
    const outsidePageSpan = {
      ...mockSpanById('span-llm-001')!,
      span_id: 'span-outside-page-001',
      parent_span_id: 'span-missing-from-page',
      name: 'Outside page span',
    };

    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        const url = new URL(request.url);
        const traceId = url.searchParams.get('filter[trace_id]');
        const data = mockSpansPage.data.filter(
          (span) => span.trace_id === traceId && span.span_id === 'span-root-001'
        );

        return HttpResponse.json({
          ...mockSpansPage,
          data,
          pagination: {
            ...mockSpansPage.pagination,
            current_page_size: data.length,
            total_results: 1001,
            total_pages: 2,
          },
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', async ({ params }) => {
        const spanId = String(params['spanId']);
        if (spanId === outsidePageSpan.span_id) {
          await delay(250);
          detailSpanIds.push(spanId);
          return HttpResponse.json(outsidePageSpan);
        }
        detailSpanIds.push(spanId);
        const span = mockSpanById(spanId);
        return span ? HttpResponse.json(span) : new HttpResponse(null, { status: 404 });
      })
    );

    renderTraceDetail('trace-agent-run-001', '?spanId=span-outside-page-001');

    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
    await user.click(screen.getByText('List'));
    expect(await screen.findByLabelText('Loading linked span')).toBeInTheDocument();
    await waitFor(() => expect(detailSpanIds).toContain('span-outside-page-001'));
    expect((await screen.findAllByText('Outside page span')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('location-search')).toHaveTextContent('spanId=span-outside-page-001');
    expect(detailSpanIds).not.toContain('span-root-001');
  });

  it('renders evaluation context only when present and filters spans to the trace', async () => {
    renderTraceDetail('trace-agent-run-001');

    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
    expect(screen.getByText('Evaluation Context')).toBeInTheDocument();
    expect(await screen.findByText('Generate final response')).toBeInTheDocument();
    expect(screen.queryByText('Retrieve deployment troubleshooting steps')).not.toBeInTheDocument();
  });

  it('omits evaluation context when the trace has none', async () => {
    renderTraceDetail('trace-agent-run-002');

    expect(
      await screen.findByText('Trace Retrieve deployment troubleshooting steps')
    ).toBeInTheDocument();
    expect(screen.queryByText('Evaluation Context')).not.toBeInTheDocument();
  });
});
