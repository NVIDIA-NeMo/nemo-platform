// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parsePreviewFrame } from '@studio/routes/AnonymizerBuilderRoute/previewApi';

describe('parsePreviewFrame', () => {
  it('reads log frames', () => {
    expect(parsePreviewFrame('{"kind":"log","level":"warning","message":"slow"}')).toEqual({
      kind: 'log',
      level: 'warning',
      message: 'slow',
    });
  });

  it('defaults an unknown log level to info', () => {
    expect(parsePreviewFrame('{"kind":"log","level":"trace","message":"x"}')).toEqual({
      kind: 'log',
      level: 'info',
      message: 'x',
    });
  });

  it('reads the trace dataset and its text column', () => {
    const line = '{"kind":"trace_dataset","records":[{"a":1}],"original_text_column":"biography"}';

    expect(parsePreviewFrame(line)).toEqual({
      kind: 'trace_dataset',
      records: [{ a: 1 }],
      originalTextColumn: 'biography',
    });
  });

  it('leaves the text column undefined when the server omits it', () => {
    expect(parsePreviewFrame('{"kind":"trace_dataset","records":[]}')).toEqual({
      kind: 'trace_dataset',
      records: [],
      originalTextColumn: undefined,
    });
  });

  it('drops record entries that are not objects', () => {
    expect(parsePreviewFrame('{"kind":"failed_records","records":[1,{"b":2}]}')).toEqual({
      kind: 'failed_records',
      records: [{ b: 2 }],
    });
  });

  it('reads the control frames', () => {
    expect(parsePreviewFrame('{"kind":"done"}')).toEqual({ kind: 'done' });
    expect(parsePreviewFrame('{"kind":"heartbeat"}')).toEqual({ kind: 'heartbeat' });
    expect(parsePreviewFrame('{"kind":"error","message":"boom"}')).toEqual({
      kind: 'error',
      message: 'boom',
    });
  });

  it('ignores blank lines, malformed JSON, and unknown frame kinds', () => {
    expect(parsePreviewFrame('  ')).toBeUndefined();
    expect(parsePreviewFrame('{not json')).toBeUndefined();
    expect(parsePreviewFrame('[1,2]')).toBeUndefined();
    expect(parsePreviewFrame('{"kind":"something_new"}')).toBeUndefined();
    expect(parsePreviewFrame('{"records":[]}')).toBeUndefined();
  });
});
