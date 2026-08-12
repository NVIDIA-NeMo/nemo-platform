// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TraceViewToolbar } from '@studio/components/IntakeDetail/TraceViewToolbar';
import type { ResolvedPluginTraceView } from '@studio/plugins/PluginTraceViewContext';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const View = () => null;

const zoomerView: ResolvedPluginTraceView = {
  pluginName: 'zoomer',
  id: 'semantic-map',
  label: 'Zoomer',
  mode: 'plugin:zoomer:semantic-map',
  View,
};

describe('TraceViewToolbar', () => {
  it('selects plugin-contributed modes beside Tree and List', async () => {
    const onViewModeChange = vi.fn();
    const user = userEvent.setup();
    render(
      <TraceViewToolbar
        viewMode="tree"
        onViewModeChange={onViewModeChange}
        pluginViews={[zoomerView]}
      />
    );

    expect(screen.getByText('Tree')).toBeInTheDocument();
    expect(screen.getByText('List')).toBeInTheDocument();
    await user.click(screen.getByText('Zoomer'));

    expect(onViewModeChange).toHaveBeenCalledWith('plugin:zoomer:semantic-map');
  });

  it('hides built-in expand and collapse actions in a plugin mode', () => {
    render(
      <TraceViewToolbar
        viewMode="plugin:zoomer:semantic-map"
        onViewModeChange={vi.fn()}
        onCollapseAll={vi.fn()}
        onExpandAll={vi.fn()}
        pluginViews={[zoomerView]}
      />
    );

    expect(screen.queryByRole('button', { name: 'Collapse all' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Expand all' })).not.toBeInTheDocument();
  });
});
