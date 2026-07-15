// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { VirtualModel } from '@nemo/sdk/generated/platform/schema';
import { VirtualModelDetailsSidePanel } from '@studio/routes/VirtualModelsListRoute/VirtualModelDetailsSidePanel';
import { renderRoute, screen } from '@studio/tests/util/render';

const vm: VirtualModel = {
  id: 'default/my-vm',
  name: 'my-vm',
  workspace: 'default',
  default_model_entity: 'default/gpt-4o',
  autoprovisioned: true,
  override_proxy: 'example-plugin.my-proxy',
  models: [{ model: 'default/gpt-4o', backend_format: null }],
  request_middleware: [
    { name: 'nemo-switchyard', config_type: 'translate', config: { target_format: 'anthropic' } },
  ],
  response_middleware: [],
  post_response_middleware: [],
  created_at: '2026-07-01T00:00:00Z',
  created_by: null,
  updated_at: '2026-07-01T00:00:00Z',
  updated_by: null,
  entity_id: 'default/my-vm',
  parent: '',
};

describe('VirtualModelDetailsSidePanel', () => {
  it('renders core fields and middleware config read-only', () => {
    renderRoute(<VirtualModelDetailsSidePanel open virtualModel={vm} onClose={() => {}} />);

    expect(screen.getByText('my-vm')).toBeInTheDocument();
    expect(screen.getAllByText('default/gpt-4o').length).toBeGreaterThan(0);
    expect(screen.getByText('example-plugin.my-proxy')).toBeInTheDocument();
    expect(screen.getByText('nemo-switchyard')).toBeInTheDocument();
    expect(screen.getByText('translate')).toBeInTheDocument();
    expect(screen.getByText(/target_format/)).toBeInTheDocument();
  });

  it('shows "None" for empty middleware pipelines', () => {
    renderRoute(<VirtualModelDetailsSidePanel open virtualModel={vm} onClose={() => {}} />);

    expect(screen.getByText('Post-response')).toBeInTheDocument();
    expect(screen.getAllByText('None').length).toBeGreaterThan(0);
  });
});
