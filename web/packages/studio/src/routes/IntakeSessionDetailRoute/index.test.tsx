// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  mockSessionById,
  mockSpanById,
  mockSpansPage,
  mockTracesPage,
} from '@studio/mocks/intake/telemetry';
import { server } from '@studio/mocks/node';
import { IntakeSessionDetailRoute } from '@studio/routes/IntakeSessionDetailRoute';
import { renderRoute, screen, waitFor, within } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
};

const renderSessionDetail = (sessionId = 'session-agent-run-001', search = '') =>
  renderRoute(undefined, {
    history: `/workspaces/default/intake/sessions/${sessionId}${search}`,
    routes: [
      {
        path: '/workspaces/:workspace/intake/sessions/:sessionId',
        element: (
          <>
            <LocationProbe />
            <IntakeSessionDetailRoute />
          </>
        ),
      },
    ],
  });

describe('IntakeSessionDetailRoute', () => {
  it('hydrates the session header and all trace trajectories with summary payloads', async () => {
    const sessionDetailRequests: string[] = [];
    const traceListRequests: URL[] = [];
    const traceDetailRequests: string[] = [];
    const spanListRequests: URL[] = [];
    const spanDetailRequests: string[] = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/sessions/:sessionId', ({ params }) => {
        const sessionId = String(params['sessionId']);
        sessionDetailRequests.push(sessionId);
        const session = mockSessionById(sessionId);
        return session ? HttpResponse.json(session) : new HttpResponse(null, { status: 404 });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/traces', ({ request }) => {
        const url = new URL(request.url);
        traceListRequests.push(url);
        const data = mockTracesPage.data
          .filter((trace) => trace.session_id === url.searchParams.get('filter[session_id]'))
          .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
        return HttpResponse.json({
          ...mockTracesPage,
          data,
          pagination: {
            ...mockTracesPage.pagination,
            current_page_size: data.length,
            total_results: data.length,
          },
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/traces/:traceId', ({ params }) => {
        traceDetailRequests.push(String(params['traceId']));
        return new HttpResponse(null, { status: 500 });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        const url = new URL(request.url);
        spanListRequests.push(url);
        const data = mockSpansPage.data.filter(
          (span) => span.session_id === url.searchParams.get('filter[session_id]')
        );
        return HttpResponse.json({
          ...mockSpansPage,
          data,
          pagination: {
            ...mockSpansPage.pagination,
            current_page_size: data.length,
            total_results: data.length,
          },
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', ({ params }) => {
        spanDetailRequests.push(String(params['spanId']));
        return new HttpResponse(null, { status: 500 });
      })
    );

    renderSessionDetail();

    expect(await screen.findByText('Session session-agent-run-001')).toBeInTheDocument();
    expect(screen.queryByText('2 traces')).not.toBeInTheDocument();
    const sessionSummary = screen.getByTestId('session-summary-header');
    expect(within(sessionSummary).getByText('6')).toBeInTheDocument();
    expect(within(sessionSummary).getByText('2,948')).toBeInTheDocument();
    expect(screen.getByText('Tree')).toBeInTheDocument();
    expect(screen.getByText('List')).toBeInTheDocument();
    expect(
      screen.queryByText('Can I deploy this model in a private workspace?')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('How do I restrict access to that private workspace?')
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /View trace/ })).not.toBeInTheDocument();
    const trajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    expect(within(trajectory).getByText('Session')).toBeInTheDocument();
    expect(
      within(trajectory).getAllByText('Answer customer policy question').length
    ).toBeGreaterThan(0);
    expect(
      within(trajectory).getAllByText('Explain private workspace access controls').length
    ).toBeGreaterThan(0);
    expect(within(trajectory).getByText('Generate final response')).toBeInTheDocument();
    expect(within(trajectory).getByText('Generate access-control guidance')).toBeInTheDocument();

    await waitFor(() => expect(traceListRequests).toHaveLength(1));
    expect(sessionDetailRequests).toEqual(['session-agent-run-001']);
    expect(traceListRequests[0].searchParams.get('filter[session_id]')).toBe(
      'session-agent-run-001'
    );
    expect(traceListRequests[0].searchParams.get('mode')).toBe('summary');
    expect(traceListRequests[0].searchParams.get('page_size')).toBe('1000');
    expect(traceListRequests[0].searchParams.get('sort')).toBe('started_at');
    expect(traceDetailRequests).toEqual([]);
    await waitFor(() => expect(spanListRequests).toHaveLength(1));
    expect(spanListRequests[0].searchParams.get('filter[trace_id]')).toBeNull();
    expect(spanListRequests[0].searchParams.get('filter[session_id]')).toBe(
      'session-agent-run-001'
    );
    expect(spanListRequests[0].searchParams.get('mode')).toBe('summary');
    expect(spanListRequests[0].searchParams.get('page_size')).toBe('1000');
    expect(spanDetailRequests).toEqual([]);
  });

  it('always sources the detail header from the session endpoint', async () => {
    const sessionDetailRequests: string[] = [];
    const session = mockSessionById('session-agent-run-001');
    expect(session).toBeDefined();
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/sessions/:sessionId', ({ params }) => {
        sessionDetailRequests.push(String(params['sessionId']));
        return HttpResponse.json({ ...session!, span_count: 47, total_tokens: 9999 });
      })
    );

    renderSessionDetail('session-agent-run-001', '?traceId=trace-agent-run-001');

    const sessionSummary = await screen.findByTestId('session-summary-header');
    expect(within(sessionSummary).getByText('47')).toBeInTheDocument();
    expect(within(sessionSummary).getByText('9,999')).toBeInTheDocument();
    expect(sessionDetailRequests).toEqual(['session-agent-run-001']);
  });

  it('navigates session to trace to span and back to the session summary', async () => {
    const user = userEvent.setup();
    renderSessionDetail();

    await screen.findByText('Session session-agent-run-001');
    const trajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    await user.click(
      within(trajectory).getAllByText('Explain private workspace access controls')[0]
    );

    expect(screen.getByText('Session session-agent-run-001')).toBeInTheDocument();
    expect(
      screen.queryByText('Trace Explain private workspace access controls')
    ).not.toBeInTheDocument();
    expect(screen.getAllByTestId('session-summary-header')).toHaveLength(1);
    expect(within(screen.getByTestId('session-summary-header')).getByText('6')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/workspaces/default/intake/sessions/session-agent-run-001?traceId=trace-agent-run-003'
    );

    await user.click(await screen.findByText('Generate access-control guidance'));
    expect(screen.getByTestId('location')).toHaveTextContent(
      '?traceId=trace-agent-run-003&spanId=span-llm-003'
    );

    await user.click(screen.getByTitle('View session'));
    expect(screen.queryByRole('link', { name: /View trace/ })).not.toBeInTheDocument();
    const restoredTrajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    expect(
      await within(restoredTrajectory).findByText('Generate final response')
    ).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/workspaces/default/intake/sessions/session-agent-run-001'
    );
  });

  it('deep-links a span from any expanded trace in the session summary', async () => {
    const user = userEvent.setup();
    renderSessionDetail();

    await screen.findByText('Session session-agent-run-001');
    const trajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    await user.click(await within(trajectory).findByText('Generate access-control guidance'));

    expect(screen.getByTestId('location')).toHaveTextContent(
      '?traceId=trace-agent-run-003&spanId=span-llm-003'
    );
    expect(
      await within(screen.getByTestId('trace-trajectory-sidebar')).findByText(
        'Generate access-control guidance'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('Session session-agent-run-001')).toBeInTheDocument();
    expect(screen.getByTestId('trace-trajectory-sidebar')).toBeInTheDocument();
  });

  it('keeps the trajectory sidebar mounted while span summaries load and fail', async () => {
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', async () => {
        await delay(100);
        return HttpResponse.json({ detail: 'Could not load span summaries' }, { status: 500 });
      })
    );

    renderSessionDetail('session-agent-run-001', '?traceId=trace-agent-run-001');

    expect(await screen.findByLabelText('Loading spans')).toBeInTheDocument();
    expect(screen.getByTestId('trace-trajectory-sidebar')).toBeInTheDocument();
    expect(await screen.findByText('Could not load span summaries')).toBeInTheDocument();
    expect(screen.getByTestId('trace-trajectory-sidebar')).toBeInTheDocument();
  });

  it('does not promote a child span error to the trace-level banner', async () => {
    const erroredChild = {
      ...mockSpanById('span-llm-001')!,
      status: 'error' as const,
      error_type: 'ChildSpanError',
      error_message: 'Only the child span failed.',
    };
    const spanDetailRequests: string[] = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', () =>
        HttpResponse.json({
          ...mockSpansPage,
          data: [erroredChild],
          pagination: {
            ...mockSpansPage.pagination,
            current_page_size: 1,
            total_results: 1,
          },
        })
      ),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', ({ params }) => {
        spanDetailRequests.push(String(params['spanId']));
        return HttpResponse.json(erroredChild);
      })
    );

    renderSessionDetail('session-agent-run-001', '?traceId=trace-agent-run-001');

    await waitFor(() => expect(spanDetailRequests).toContain(erroredChild.span_id));
    await waitFor(() => {
      expect(screen.getAllByText('Only the child span failed.')).toHaveLength(1);
    });
  });

  it('preserves the session view mode when selecting a trace', async () => {
    const user = userEvent.setup();
    renderSessionDetail();

    await screen.findByText('Session session-agent-run-001');
    await user.click(screen.getByText('List'));
    const trajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    await user.click(
      within(trajectory).getAllByText('Explain private workspace access controls')[0]
    );

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('?traceId=trace-agent-run-003');
    });
    expect(screen.queryByTestId('trace-trajectory-sidebar')).not.toBeInTheDocument();
    expect(await screen.findByText('Generate access-control guidance')).toBeInTheDocument();
  });

  it('keeps the detail shell useful for a session with one trace', async () => {
    renderSessionDetail('session-agent-run-002');

    expect(await screen.findByText('Session session-agent-run-002')).toBeInTheDocument();
    expect(screen.queryByText('1 trace')).not.toBeInTheDocument();
    expect(within(screen.getByTestId('session-summary-header')).getByText('3')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /View trace/ })).not.toBeInTheDocument();
    const trajectory = screen.getByRole('navigation', { name: 'Trace trajectory' });
    expect(within(trajectory).getByText('Session')).toBeInTheDocument();
    expect(
      (await within(trajectory).findAllByText('Retrieve deployment troubleshooting steps')).length
    ).toBeGreaterThan(0);
  });

  it('restores a span deep link without first loading the root span detail', async () => {
    const detailSpanIds: string[] = [];
    const spanListModes: Array<string | null> = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        const url = new URL(request.url);
        spanListModes.push(url.searchParams.get('mode'));
        const sessionId = url.searchParams.get('filter[session_id]');
        const data = mockSpansPage.data.filter((span) => span.session_id === sessionId);
        return HttpResponse.json({
          ...mockSpansPage,
          data,
          pagination: {
            ...mockSpansPage.pagination,
            current_page_size: data.length,
            total_results: data.length,
          },
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', ({ params }) => {
        const spanId = String(params['spanId']);
        detailSpanIds.push(spanId);
        const span = mockSpanById(spanId);
        return span ? HttpResponse.json(span) : new HttpResponse(null, { status: 404 });
      })
    );

    renderSessionDetail(
      'session-agent-run-001',
      '?traceId=trace-agent-run-001&spanId=span-llm-001'
    );

    expect((await screen.findAllByText('Generate final response')).length).toBeGreaterThan(0);
    expect(screen.getByText('Session session-agent-run-001')).toBeInTheDocument();
    await waitFor(() => expect(detailSpanIds).toContain('span-llm-001'));
    expect(spanListModes).toEqual(['summary']);
    expect(detailSpanIds).not.toContain('span-root-001');
  });

  it('preserves a directly linked span outside the loaded summary page', async () => {
    const user = userEvent.setup();
    const outsidePageSpan = {
      ...mockSpanById('span-llm-001')!,
      span_id: 'span-outside-page-001',
      parent_span_id: 'span-missing-from-page',
      name: 'Outside page span',
    };

    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        const sessionId = new URL(request.url).searchParams.get('filter[session_id]');
        const data = mockSpansPage.data.filter(
          (span) => span.session_id === sessionId && span.span_id === 'span-root-001'
        );
        return HttpResponse.json({
          ...mockSpansPage,
          data,
          pagination: { ...mockSpansPage.pagination, total_results: 1001, total_pages: 2 },
        });
      }),
      http.get('*/apis/intake/v2/workspaces/:workspace/spans/:spanId', async ({ params }) => {
        if (params['spanId'] === outsidePageSpan.span_id) {
          await delay(100);
          return HttpResponse.json(outsidePageSpan);
        }
        const span = mockSpanById(String(params['spanId']));
        return span ? HttpResponse.json(span) : new HttpResponse(null, { status: 404 });
      })
    );

    renderSessionDetail(
      'session-agent-run-001',
      '?traceId=trace-agent-run-001&spanId=span-outside-page-001'
    );

    await user.click(await screen.findByText('List'));
    expect(await screen.findByLabelText('Loading linked span')).toBeInTheDocument();
    expect((await screen.findAllByText('Outside page span')).length).toBeGreaterThan(0);
  });

  it('rejects a trace deep link that belongs to another session', async () => {
    renderSessionDetail('session-agent-run-001', '?traceId=trace-agent-run-002');

    expect(await screen.findByText('Trace Not Found')).toBeInTheDocument();
    expect(screen.getByText(/does not belong to this session/)).toBeInTheDocument();
  });
});
