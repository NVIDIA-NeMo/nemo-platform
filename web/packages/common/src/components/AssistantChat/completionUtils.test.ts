// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChatCompletionChunk } from 'openai/resources/index.mjs';
import type { Stream } from 'openai/streaming.mjs';

import { getCompletionImages, isChatCompletionStream } from './completionUtils';

describe('isChatCompletionStream', () => {
  it('returns false for nullish values', () => {
    expect(isChatCompletionStream(null)).toBe(false);
    expect(isChatCompletionStream(undefined)).toBe(false);
  });

  it('detects async iterable completion streams', () => {
    const stream = {
      controller: new AbortController(),
      async *[Symbol.asyncIterator]() {
        yield {} as ChatCompletionChunk;
      },
    } as unknown as Stream<ChatCompletionChunk>;

    expect(isChatCompletionStream(stream)).toBe(true);
  });
});

describe('getCompletionImages', () => {
  it('extracts base64 image URLs from an image-model stream delta', () => {
    const imageUrl = 'data:image/png;base64,iVBORw0KGgo=';

    expect(
      getCompletionImages({
        choices: [{ delta: { images: [{ image_url: { url: imageUrl } }] } }],
      })
    ).toEqual([{ type: 'image', image: imageUrl }]);
  });

  it('ignores non-image and non-data URLs', () => {
    expect(
      getCompletionImages({
        choices: [
          {
            delta: {
              images: [
                { image_url: { url: 'https://example.com/image.png' } },
                { image_url: { url: 'data:text/plain;base64,SGVsbG8=' } },
              ],
            },
          },
        ],
      })
    ).toEqual([]);
  });
});
