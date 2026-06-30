// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Divider, Stack, Tag, Text } from '@nvidia/foundations-react-core';
import { TaskDisplay } from '@studio/components/evaluation/Configurations/TaskDisplay';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  type EvaluationConfig,
  getCustomConfigTaskEntries,
} from '@studio/selectors/evaluationConfig';
import { FC, Fragment } from 'react';

export interface ConfigurationDetailsPanelProps {
  /** The configuration to display */
  config: EvaluationConfig;
  /** Optional tags to display */
  tags?: string[];
  /** Optional CSS class name */
  className?: string;
}

/**
 * Reusable component to display evaluation configuration details in read-only mode.
 * Supports configurations with multiple tasks.
 * Can be used in multiple contexts: launch evaluation form, config table side panel, config details page.
 *
 * @example
 * // In a form context
 * <ConfigurationDetailsPanel config={selectedConfig} tags={formData.jobTags} />
 *
 * @example
 * // In a table side panel
 * <ConfigurationDetailsPanel config={selectedConfig} />
 */
export const ConfigurationDetailsPanel: FC<ConfigurationDetailsPanelProps> = ({
  config,
  tags,
  className,
}) => {
  const workspace = useWorkspaceFromPath();

  // Extract configuration data
  const configName = config.name || '-';
  const configId = config.id || '-';
  const tasks = getCustomConfigTaskEntries(config);

  return (
    <Stack gap="density-2xl" className={`overflow-y-auto w-full ${className || ''}`}>
      <Stack gap="density-2xl" className="w-full">
        <KVPair label="Configuration Name" value={configName} />
        <KVPair label="Configuration ID" value={configId} />

        {tags && tags.length > 0 && (
          <KVPair
            label="Tags"
            value={
              <Stack gap="density-sm" direction="row">
                {tags.map((tag: string) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </Stack>
            }
          />
        )}
      </Stack>

      {/* Tasks Section */}
      <Text kind="label/bold/lg">Tasks</Text>
      <Stack gap="density-2xl" className="w-full">
        {tasks.length === 0 ? (
          <Text kind="body/regular/sm" color="disabled">
            No tasks configured
          </Text>
        ) : (
          tasks.map(([taskName, task], index) => (
            <Fragment key={taskName}>
              <TaskDisplay taskName={taskName} task={task} workspace={workspace} />
              {/* Show divider between tasks (not after the last one) */}
              {index < tasks.length - 1 && <Divider />}
            </Fragment>
          ))
        )}
      </Stack>
    </Stack>
  );
};
