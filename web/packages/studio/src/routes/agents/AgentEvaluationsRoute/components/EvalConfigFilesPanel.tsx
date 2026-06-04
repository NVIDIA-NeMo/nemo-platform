// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Accordion, Block, Panel, Text } from '@nvidia/foundations-react-core';
import type { EvalConfigFile } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { FileCode } from 'lucide-react';
import type { FC } from 'react';

const PRETTY_NAME: Record<string, string> = {
  'config_original.yml': 'Original eval config',
  'config_effective.yml': 'Effective eval config',
  'config_metadata.json': 'Run metadata',
};

interface EvalConfigFilesPanelProps {
  files: EvalConfigFile[];
}

export const EvalConfigFilesPanel: FC<EvalConfigFilesPanelProps> = ({ files }) => {
  return (
    <Panel
      slotHeading="Run configuration"
      slotIcon={<FileCode />}
      elevation="high"
      density="compact"
    >
      {files.length === 0 ? (
        <Block className="text-subtle">No config snapshots in the output fileset.</Block>
      ) : (
        <Accordion
          multiple
          items={files.map((f) => ({
            chevronPosition: 'start',
            value: f.name,
            slotTrigger: <Text kind="body/semibold/sm">{PRETTY_NAME[f.name] ?? f.name}</Text>,
            slotContent: (
              <Block>
                <pre className="font-mono text-xs whitespace-pre-wrap break-all max-h-96 overflow-auto bg-surface-subtle p-density-lg rounded leading-relaxed">
                  {f.content}
                </pre>
              </Block>
            ),
          }))}
        />
      )}
    </Panel>
  );
};
