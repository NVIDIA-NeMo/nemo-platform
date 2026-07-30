// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Preview } from '@storybook/react';
import type { RequestHandler } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupWorker } from 'msw/browser';
import { useEffect, useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import '../../studio/src/index.css';

const worker = setupWorker();
const workerReady = worker.start({ onUnhandledRequest: 'bypass' });

const preview: Preview = {
  loaders: [() => workerReady],
  globalTypes: {
    theme: {
      name: 'Theme',
      description: 'Light or dark theme',
      defaultValue: 'dark',
      toolbar: {
        icon: 'circlehollow',
        items: [
          { value: 'light', title: 'Light', icon: 'sun' },
          { value: 'dark', title: 'Dark', icon: 'moon' },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [
    (Story, context) => {
      const handlers = (context.parameters?.msw?.handlers ?? []) as RequestHandler[];
      worker.resetHandlers(...handlers);
      return <Story />;
    },
    (Story, context) => {
      const theme = context.globals.theme ?? 'dark';
      const themeClass = theme === 'dark' ? 'nv-dark' : 'nv-light';
      const [queryClient] = useState(
        () => new QueryClient({ defaultOptions: { queries: { retry: false } } })
      );

      useEffect(() => {
        document.documentElement.classList.remove('nv-dark', 'nv-light');
        document.documentElement.classList.add(themeClass);
        return () => {
          document.documentElement.classList.remove(themeClass);
        };
      }, [themeClass]);

      const initialPath = (context.parameters?.router?.initialPath as string) ?? '/';

      return (
        <MemoryRouter initialEntries={[initialPath]}>
          <QueryClientProvider client={queryClient}>
            <div id="app" className={themeClass} style={{ minHeight: '100vh', padding: '1rem' }}>
              <Story />
            </div>
          </QueryClientProvider>
        </MemoryRouter>
      );
    },
  ],
  parameters: {
    layout: 'padded',
    backgrounds: { disable: true },
    a11y: { test: 'todo' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
