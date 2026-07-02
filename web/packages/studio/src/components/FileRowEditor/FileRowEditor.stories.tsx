// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import type { Meta, StoryObj } from '@storybook/react';
import { FileRowEditor } from '@studio/components/FileRowEditor';
import { SAMPLE_ROWS } from '@studio/components/FileRowEditor/sampleRows';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';

const meta = {
  component: FileRowEditor,
  title: 'Components/FileRowEditor',
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <div className="h-dvh min-w-[1100px]">
        <ToastProvider>
          <Story />
        </ToastProvider>
      </div>
    ),
  ],
} satisfies Meta<typeof FileRowEditor>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default viewer with the sample SFT dataset; the schema is inferred from the rows. */
export const Default: Story = {
  args: {
    initialRows: SAMPLE_ROWS,
  },
};

/**
 * A completely different shape (CSV-style orders). Nothing about the editor is tied to
 * the SFT schema — columns, types, filters, and editor controls are derived from the data.
 */
export const DifferentShape: Story = {
  args: {
    fileName: 'orders-2026-q2.csv',
    fileSizeLabel: '812 KB',
    initialRows: [
      {
        order_id: 'A-1001',
        customer: 'Acme Corp',
        total: 1299.5,
        shipped: true,
        region: 'NA',
        line_items: [{ sku: 'GPU-A100', qty: 1 }],
      },
      {
        order_id: 'A-1002',
        customer: 'Globex',
        total: 49.99,
        shipped: false,
        region: 'EU',
        line_items: [{ sku: 'CABLE-3M', qty: 4 }],
      },
      {
        order_id: 'A-1003',
        customer: 'Initech',
        total: 8800,
        shipped: true,
        region: 'NA',
        line_items: [{ sku: 'DGX-STATION', qty: 1 }],
      },
      {
        order_id: 'A-1004',
        customer: 'Umbrella',
        total: 320.25,
        shipped: false,
        region: 'APAC',
        line_items: [{ sku: 'NVLINK', qty: 2 }],
      },
      {
        order_id: 'A-1005',
        customer: 'Soylent',
        total: 15.0,
        shipped: true,
        region: 'EU',
        line_items: [{ sku: 'STICKER', qty: 10 }],
      },
    ] satisfies DataFileRow[],
  },
};

/**
 * Empty file. With no rows to infer from, the schema is supplied via `columns` so the
 * "Add Row" affordance can build a typed blank row.
 */
export const Empty: Story = {
  args: {
    fileName: 'new-dataset.jsonl',
    fileSizeLabel: '0 B',
    initialRows: [],
    columns: [
      { key: 'prompt', label: 'prompt', type: 'string', multiline: true },
      { key: 'completion', label: 'completion', type: 'string', multiline: true },
      // Explicit enum options → the editor renders a single-select dropdown.
      { key: 'split', label: 'split', type: 'string', options: ['train', 'validation', 'test'] },
      { key: 'score', label: 'score', type: 'float' },
    ],
  },
};
