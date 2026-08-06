// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Read a newline-delimited response body, invoking `onLine` per line. A read rarely lands on a
 * line boundary, so the trailing partial is held back until the next chunk completes it, then
 * flushed at EOF. Callers decide what a blank line means.
 */
export const readLineDelimitedStream = async (
  body: NonNullable<Response['body']>,
  onLine: (line: string) => void
): Promise<void> => {
  const reader = body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    lines.forEach(onLine);
  }

  onLine(buffer);
};
