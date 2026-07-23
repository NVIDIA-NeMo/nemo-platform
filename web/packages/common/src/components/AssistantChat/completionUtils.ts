// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChatCompletion, ChatCompletionChunk } from 'openai/resources/index.mjs';
import type { Stream } from 'openai/streaming.mjs';

interface ImageResponsePart {
  type: 'image';
  image: string;
}

const isImageDataUrl = (value: unknown): value is string =>
  typeof value === 'string' && /^data:image\/[a-z0-9.+-]+;base64,/i.test(value);

/**
 * Extracts image data URLs from OpenAI-compatible image-model extensions.
 *
 * Some image providers return generated images in `images[].image_url.url`,
 * which is not part of the OpenAI SDK's ChatCompletionChunk type. Keep this
 * narrow so arbitrary provider extensions cannot become renderable image URLs.
 */
export const getCompletionImages = (completion: unknown): ImageResponsePart[] => {
  if (typeof completion !== 'object' || completion === null || !('choices' in completion)) {
    return [];
  }

  const firstChoice = Array.isArray(completion.choices) ? completion.choices[0] : undefined;
  if (typeof firstChoice !== 'object' || firstChoice === null) {
    return [];
  }

  const responsePart =
    'delta' in firstChoice
      ? firstChoice.delta
      : 'message' in firstChoice
        ? firstChoice.message
        : null;
  if (typeof responsePart !== 'object' || responsePart === null || !('images' in responsePart)) {
    return [];
  }

  const images = responsePart.images;
  if (!Array.isArray(images)) return [];

  return images.flatMap((image) => {
    if (typeof image !== 'object' || image === null || !('image_url' in image)) return [];
    const imageUrl = image.image_url;
    if (typeof imageUrl !== 'object' || imageUrl === null || !('url' in imageUrl)) return [];

    return isImageDataUrl(imageUrl.url) ? [{ type: 'image', image: imageUrl.url }] : [];
  });
};

export const isChatCompletionStream = (
  value: ChatCompletion | Stream<ChatCompletionChunk> | null | undefined
): value is Stream<ChatCompletionChunk> =>
  value != null && typeof value === 'object' && Symbol.asyncIterator in value;

export const isAbortError = (error: unknown): boolean => {
  if (!(error instanceof Error)) return false;
  return error.name === 'AbortError' || error.name === 'APIUserAbortError';
};

export const getCompletionText = (completion: ChatCompletion): string => {
  const content = completion.choices[0]?.message.content;
  return typeof content === 'string' ? content : '';
};
