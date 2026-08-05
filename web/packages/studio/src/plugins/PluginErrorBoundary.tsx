// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { Button, PageHeader, Panel, Stack } from '@nvidia/foundations-react-core';
import { logger } from '@studio/util/logger';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface PluginErrorBoundaryProps {
  // Changing this resets the boundary.
  pluginName: string;
  children: ReactNode;
}

interface PluginErrorBoundaryState {
  error: Error | null;
}

// Contains a plugin's render errors to its own panel so a throw in third-party
// plugin code can't unwind past Studio's layout.
export class PluginErrorBoundary extends Component<
  PluginErrorBoundaryProps,
  PluginErrorBoundaryState
> {
  state: PluginErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PluginErrorBoundaryState {
    return { error };
  }

  componentDidUpdate(prevProps: PluginErrorBoundaryProps): void {
    if (this.state.error && prevProps.pluginName !== this.props.pluginName) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logger.error(
      `Plugin "${this.props.pluginName}" crashed during render: ${error.message}`,
      info.componentStack
    );
  }

  private reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <Stack className="h-full" padding="4" gap="3">
        <PageHeader slotHeading={`Plugin: ${this.props.pluginName}`} />
        <Panel className="flex-1 justify-center" elevation="high">
          <ErrorMessage
            header="This plugin ran into a problem"
            message={error.message || 'The plugin failed to render.'}
            slotFooter={
              <Button kind="secondary" onClick={this.reset}>
                Try Again
              </Button>
            }
          />
        </Panel>
      </Stack>
    );
  }
}
