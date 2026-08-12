// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PluginErrorBoundary } from '@studio/plugins/PluginErrorBoundary';
import type { ResolvedPluginTraceView } from '@studio/plugins/PluginTraceViewContext';
import type { PluginTrace } from '@studio/plugins/types';
import { usePluginHost } from '@studio/plugins/usePluginHost';
import { type FC, type ReactElement } from 'react';

interface PluginTraceViewRendererProps {
  view: ResolvedPluginTraceView;
  trace: PluginTrace;
}

interface PluginTraceViewActivityContentProps extends PluginTraceViewRendererProps {
  Activity: NonNullable<ResolvedPluginTraceView['Activity']>;
}

export const PluginTraceViewRenderer: FC<PluginTraceViewRendererProps> = ({ view, trace }) => {
  const host = usePluginHost(view.pluginName);
  const { View } = view;
  return (
    <PluginErrorBoundary pluginName={view.pluginName}>
      <View host={host} trace={trace} />
    </PluginErrorBoundary>
  );
};

const PluginTraceViewActivityContent: FC<PluginTraceViewActivityContentProps> = ({
  view,
  trace,
  Activity,
}) => {
  const host = usePluginHost(view.pluginName);
  return (
    <PluginErrorBoundary pluginName={view.pluginName} fallback={null}>
      <Activity host={host} trace={trace} />
    </PluginErrorBoundary>
  );
};

export const PluginTraceViewActivity = ({
  view,
  trace,
}: PluginTraceViewRendererProps): ReactElement | null =>
  view.Activity ? (
    <PluginTraceViewActivityContent view={view} trace={trace} Activity={view.Activity} />
  ) : null;
