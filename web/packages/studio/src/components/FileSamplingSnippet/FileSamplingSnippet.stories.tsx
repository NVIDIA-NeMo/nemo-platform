// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import {
  Stack,
  Text,
  ThemeProvider as KaizenThemeProvider,
  type Theme,
} from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { FileSamplingSnippet } from '@studio/components/FileSamplingSnippet/FileSamplingSnippet';
import { http, HttpResponse } from 'msw';
import { type ComponentProps, useState } from 'react';

/** Matches `/apis/files/v2/workspaces/:ws/filesets/:name/-/encoded-path` (download + head). */
const FILES_FILESET_OBJECT_REGEX = /\/apis\/files\/v2\/workspaces\/[^/]+\/filesets\/[^/]+\/-\/.+/;

const SAMPLE_JSONL = [
  '{"prompt":"Summarize the following text.","meta":{"id":"a"}}',
  '{"prompt":"Translate to French: hello","meta":{"id":"b"}}',
  '{"instruction":"What is 2+2?","answer":"4"}',
  '{"prompt":"Fourth line for sampling edge cases","score":0.95}',
].join('\n');

const mockFileSuccessHandlers = [
  http.head(FILES_FILESET_OBJECT_REGEX, () => new HttpResponse(null, { status: 200 })),
  http.get(FILES_FILESET_OBJECT_REGEX, () => {
    const blob = new Blob([SAMPLE_JSONL], { type: 'application/octet-stream' });
    return new HttpResponse(blob, { status: 200 });
  }),
];

const NOOP_SAMPLE = () => {};

const meta = {
  component: FileSamplingSnippet,
  title: 'Components/File Sampling/Snippet',
  decorators: [
    (Story, context) => {
      const sbTheme = (context.globals.theme === 'light' ? 'light' : 'dark') as Theme;
      return (
        <KaizenThemeProvider density="standard" global={false} theme={sbTheme}>
          <ToastProvider>
            <Story />
          </ToastProvider>
        </KaizenThemeProvider>
      );
    },
  ],
  parameters: {
    layout: 'padded',
    msw: {
      handlers: mockFileSuccessHandlers,
    },
  },
  args: {
    workspace: 'default',
    filesetName: 'story-fileset',
    filePath: 'eval/sample.jsonl',
    maxSampleRows: 10,
    sampleMethod: 'head' as const,
    displayMode: 'code' as const,
    onSampledContentChange: NOOP_SAMPLE,
  },
} satisfies Meta<typeof FileSamplingSnippet>;

export default meta;
type Story = StoryObj<typeof meta>;

/** JSONL preview via {@link CodeEditor}; sampling is head + max 10 rows by default. */
export const CodeHeadSample: Story = {
  name: 'Code head sample',
};

/** Same file content shown as a dynamic-column table (JSON objects per line). */
export const TableView: Story = {
  name: 'Table view',
  args: {
    displayMode: 'table',
    sampleMethod: 'head',
    maxSampleRows: 3,
  },
};

/** Tail sampling — last lines of the file text after stripping empty lines. */
export const TailSample: Story = {
  name: 'Tail sample',
  args: {
    sampleMethod: 'tail',
    maxSampleRows: 2,
  },
};

/** HEAD/download fail — error banner and empty editor. */
export const FileLoadError: Story = {
  name: 'File load error',
  parameters: {
    msw: {
      handlers: [
        http.head(FILES_FILESET_OBJECT_REGEX, () => new HttpResponse(null, { status: 404 })),
        http.get(FILES_FILESET_OBJECT_REGEX, () => new HttpResponse(null, { status: 404 })),
      ],
    },
  },
};

/** Slow file fetch — spinner while content loads. */
export const Loading: Story = {
  name: 'Loading',
  parameters: {
    msw: {
      handlers: [
        http.head(FILES_FILESET_OBJECT_REGEX, async () => {
          await new Promise((resolve) => setTimeout(resolve, 60_000));
          return new HttpResponse(null, { status: 200 });
        }),
        http.get(FILES_FILESET_OBJECT_REGEX, async () => {
          await new Promise((resolve) => setTimeout(resolve, 60_000));
          const blob = new Blob([SAMPLE_JSONL], { type: 'application/octet-stream' });
          return new HttpResponse(blob, { status: 200 });
        }),
      ],
    },
  },
};

/** Optional footer slot (e.g. evaluation limits copy). */
export const WithFooter: Story = {
  name: 'With footer',
  args: {
    slotFooter: (
      <Text kind="label/regular/sm" className="text-secondary">
        Live sampling is capped for interactive use; run jobs for full datasets.
      </Text>
    ),
  },
};

function CallbackPreviewHarness(props: ComponentProps<typeof FileSamplingSnippet>) {
  const [sampled, setSampled] = useState('');
  return (
    <Stack gap="density-lg" className="max-w-3xl">
      <FileSamplingSnippet
        {...props}
        onSampledContentChange={(text) => {
          setSampled(text);
        }}
      />
      <Text kind="body/regular/sm" className="text-secondary">
        Last <code className="font-mono">onSampledContentChange</code> payload length:{' '}
        <strong>{sampled.length}</strong> chars
      </Text>
    </Stack>
  );
}

/** Demonstrates the sampled text callback (character count updates after load). */
export const CallbackPreview: Story = {
  name: 'Callback preview',
  render: (args) => <CallbackPreviewHarness {...args} />,
  parameters: {
    msw: {
      handlers: mockFileSuccessHandlers,
    },
  },
};
