// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetFileBlockingInput } from '@studio/components/agents/AgentBlockingInput/FilesetFileBlockingInput';
import type { FilesetFileBlockingInputProps } from '@studio/components/agents/AgentBlockingInput/types';
import { getStringValue } from '@studio/components/agents/AgentBlockingInput/utils';
import { SAMPLE_EVAL_CONFIG_PATH } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import { evalFilesetForAgent } from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import type { FC } from 'react';

const DEFAULT_ACCEPTED_FILE_TYPES = ['.yml', '.yaml'] as const;

export const EvalConfigBlockingInput: FC<FilesetFileBlockingInputProps> = (props) => {
  const input = props.input ?? {};
  const agent = getStringValue(input, 'agent') ?? getStringValue(input, 'default_agent');
  const sampleConfigFileset = agent ? evalFilesetForAgent(agent) : undefined;

  return (
    <FilesetFileBlockingInput
      {...props}
      defaultAcceptedFileTypes={[...DEFAULT_ACCEPTED_FILE_TYPES]}
      missingSelectionMessage="Pick an eval YAML inside an existing fileset"
      secondaryActions={[
        {
          disabled: !agent,
          label: 'Use sample config',
          onClick: () =>
            props.onSubmit({
              displayText: 'Use sample evaluation config',
              value: {
                use_sample_eval_config: true,
                ...(agent ? { agent } : {}),
                eval_config: SAMPLE_EVAL_CONFIG_PATH,
                ...(sampleConfigFileset ? { eval_config_fileset: sampleConfigFileset } : {}),
              },
            }),
        },
      ]}
      secondaryActionLabel="I don't have a config"
      onSecondaryAction={() =>
        props.onSubmit({
          displayText: "I don't have an evaluation config yet",
          value: { needs_eval_config: true },
        })
      }
      selectionDisplayLabel="Selected eval config"
      submitLabel="Select eval config"
      toValue={({ name, objectPath }) => ({
        eval_config: objectPath,
        eval_config_fileset: name,
      })}
    />
  );
};
