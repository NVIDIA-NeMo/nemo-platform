// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* eslint-disable no-console */
import { handlers } from '@studio/mocks/handlers';
import { handlers as iconsHandlers } from '@studio/mocks/icons';
import { setupServer } from 'msw/node';

export const server = setupServer(...handlers, ...iconsHandlers);

if (process.env.DEBUG_MSW_HANDLERS) {
  server.events.on('request:unhandled', ({ request }) => {
    console.warn('Request unhandled:', request.method, request.url.toString());
  });

  server.events.on('response:mocked', ({ request }) => {
    console.warn('Request mocked:', request.method, request.url.toString());
  });

  server.events.on('response:bypass', ({ request }) => {
    console.warn('Request bypassed:', request.method, request.url.toString());
  });
}
