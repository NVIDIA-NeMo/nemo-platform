// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { server } from '@studio/mocks/node';
import { InsightTracesTable } from '@studio/routes/optimizer/InsightTracesTable';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const makeTrace = (sequence: number): Trace => ({
  id: `trace-${String(sequence).padStart(2, '0')}`,
  session_id: `session-${sequence}`,
  workspace: DEFAULT_WORKSPACE,
  name: `Trace ${String(sequence).padStart(2, '0')}`,
  started_at: `2026-07-20T12:${String(sequence).padStart(2, '0')}:00Z`,
  status: 'success',
});

const installTraceHandler = ({
  traces,
  failedIds = [],
}: {
  traces: Trace[];
  failedIds?: string[];
}) => {
  const requests: Array<{ id: string; mode: string | null }> = [];
  const tracesById = new Map(traces.map((trace) => [trace.id, trace]));

  server.use(
    http.get('*/apis/intake/v2/workspaces/:workspace/traces/:traceId', ({ params, request }) => {
      const id = String(params['traceId']);
      requests.push({ id, mode: new URL(request.url).searchParams.get('mode') });

      if (failedIds.includes(id)) {
        return HttpResponse.json({ detail: `Could not load ${id}` }, { status: 500 });
      }

      return HttpResponse.json(tracesById.get(id));
    })
  );

  return requests;
};

describe('InsightTracesTable', () => {
  it('requests and displays only the current page in reference order using preview mode', async () => {
    const user = userEvent.setup();
    const traces = Array.from({ length: 11 }, (_, index) => makeTrace(index + 1));
    const traceIds = traces.map((trace) => trace.id);
    const requests = installTraceHandler({ traces });

    renderRoute(<InsightTracesTable workspace={DEFAULT_WORKSPACE} traceIds={traceIds} />, {
      history: '/optimizer?page_size=10',
    });

    await screen.findByText('Trace 01');
    await waitFor(() =>
      expect(requests).toEqual(
        traceIds.slice(0, 10).map((id) => ({
          id,
          mode: 'preview',
        }))
      )
    );
    expect(screen.queryByText('Trace 11')).not.toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('Trace 01');
    expect(rows[2]).toHaveTextContent('Trace 02');
    expect(screen.getByText('1-10 of 11 items')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /next page/i }));

    expect(await screen.findByText('Trace 11')).toBeInTheDocument();
    await waitFor(() => expect(requests.map(({ id }) => id)).toEqual(traceIds));
    expect(screen.queryByText('Trace 01')).not.toBeInTheDocument();
    expect(screen.getByText('11-11 of 11 items')).toBeInTheDocument();
  });

  it('keeps successful rows visible when part of the current page fails', async () => {
    const traces = [makeTrace(1), makeTrace(2)];
    installTraceHandler({ traces, failedIds: [traces[1].id] });

    renderRoute(
      <InsightTracesTable
        workspace={DEFAULT_WORKSPACE}
        traceIds={traces.map((trace) => trace.id)}
      />
    );

    expect(await screen.findByText('Trace 01')).toBeInTheDocument();
    expect(screen.getByText("1 of 2 traces couldn't be loaded.")).toBeInTheDocument();
    expect(screen.getByText('1-2 of 2 items')).toBeInTheDocument();
  });

  it('shows an error instead of an empty state when every current-page request fails', async () => {
    const traces = [makeTrace(1), makeTrace(2)];
    installTraceHandler({ traces, failedIds: traces.map((trace) => trace.id) });

    renderRoute(
      <InsightTracesTable
        workspace={DEFAULT_WORKSPACE}
        traceIds={traces.map((trace) => trace.id)}
      />
    );

    expect(await screen.findByText('Error')).toBeInTheDocument();
    expect(screen.queryByText('This insight has no linked traces.')).not.toBeInTheDocument();
  });
});
