// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEntityReference } from '@nemo/common/src/namedEntity';
import { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { DatasetInfoModal } from '@studio/components/DatasetInfoModal';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { dataset } from '@studio/mocks/datasets';
import { files } from '@studio/mocks/datasets/files';
import { server } from '@studio/mocks/node';
import { render, screen } from '@studio/tests/util/render';
import { http, HttpResponse } from 'msw';

describe('DatasetInfoModal', () => {
  it('renders modal with loading', () => {
    render(<DatasetInfoModal onClose={vi.fn()} open dataset={dataset} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders modal with dataset title if name present', async () => {
    render(<DatasetInfoModal onClose={vi.fn()} open dataset={dataset} />);

    expect(await screen.findByText(`Dataset: ${dataset.name}`)).toBeInTheDocument();
  });

  it('renders only maximum files provided', async () => {
    const maxFiles = 2;
    server.use(
      http.get<never, never, FilesetFileOutput[]>(
        `${PLATFORM_BASE_URL}/v1/hf/api/datasets/${getEntityReference(dataset)}/tree/main`,
        () => {
          return HttpResponse.json(files);
        }
      )
    );

    render(<DatasetInfoModal onClose={vi.fn()} open dataset={dataset} maxFiles={maxFiles} />);

    expect(await screen.findByText(`Dataset: ${dataset.name}`)).toBeInTheDocument();
    expect(
      await screen.findByText(
        `...and ${files.length - maxFiles} additional file(s) omitted from display`
      )
    );
  });
});
