// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { FilesetListRoute } from '@studio/routes/FilesetListRoute';
import { render, screen } from '@studio/tests/util/render';

// Force the feature flag on so external filesets resolve to the dedicated
// detail route. The flag is a preview flag and defaults off in tests.
vi.mock('@studio/constants/environment', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@studio/constants/environment')>();
  return { ...actual, FILESET_DETAILS_ENABLED: true };
});

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

// Stub the table so we can exercise the `getDatasetRoute` prop directly with a
// local and an external fileset fixture, rather than driving a full row click.
vi.mock('@studio/components/DatasetsTable', () => ({
  DatasetsTable: ({ getDatasetRoute }: { getDatasetRoute: (d: FilesetOutput) => string }) => {
    const local = { workspace: 'default', name: 'local-fs', storage: { type: 'local' } };
    const external = { workspace: 'default', name: 'hf-fs', storage: { type: 'huggingface' } };
    return (
      <div>
        <div data-testid="local-route">{getDatasetRoute(local as unknown as FilesetOutput)}</div>
        <div data-testid="external-route">
          {getDatasetRoute(external as unknown as FilesetOutput)}
        </div>
      </div>
    );
  },
}));

// Lightweight stubs for the rest of the page so the test stays focused.
vi.mock('@studio/routes/FilesetListRoute/PanelManagement', () => ({
  PanelManagement: () => null,
}));
vi.mock('@studio/components/NewDatasetButton', () => ({ NewDatasetButton: () => null }));
vi.mock('@studio/components/NewModelFilesetButton', () => ({ NewModelFilesetButton: () => null }));

describe('FilesetListRoute getDatasetRoute (feature flag on)', () => {
  it('routes external filesets to the dedicated detail route and keeps local filesets on the panel route', () => {
    render(<FilesetListRoute />);

    expect(screen.getByTestId('external-route')).toHaveTextContent(
      '/workspaces/default/filesets/default%2Fhf-fs/details'
    );
    expect(screen.getByTestId('local-route')).toHaveTextContent(
      '/workspaces/default/filesets/default%2Flocal-fs'
    );
    expect(screen.getByTestId('local-route').textContent).not.toContain('/details');
  });
});
