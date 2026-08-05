// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { readLineDelimitedStream } from '@studio/util/lineStream';

const streamOf = (chunks: string[]): NonNullable<Response['body']> => {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
};

const collect = async (chunks: string[]): Promise<string[]> => {
  const lines: string[] = [];
  await readLineDelimitedStream(streamOf(chunks), (line) => lines.push(line));
  return lines;
};

describe('readLineDelimitedStream', () => {
  it('splits a single chunk on newlines', async () => {
    expect(await collect(['a\nb\nc'])).toEqual(['a', 'b', 'c']);
  });

  it('rejoins a line split across chunk boundaries', async () => {
    expect(await collect(['{"ki', 'nd":"do', 'ne"}\n'])).toEqual(['{"kind":"done"}', '']);
  });

  it('holds back the trailing partial until the next chunk completes it', async () => {
    expect(await collect(['a\nb', 'c\nd'])).toEqual(['a', 'bc', 'd']);
  });

  it('flushes whatever is left at end of stream', async () => {
    expect(await collect(['only'])).toEqual(['only']);
  });

  it('emits an empty final line for a newline-terminated body', async () => {
    expect(await collect(['a\n'])).toEqual(['a', '']);
  });

  it('handles an empty body', async () => {
    expect(await collect([])).toEqual(['']);
  });
});
