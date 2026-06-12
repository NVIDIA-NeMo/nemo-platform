// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvalConfigBlockingInput } from '@studio/components/agents/AgentBlockingInput/EvalConfigBlockingInput';
import type {
  AgentBlockingInputRequest,
  AgentBlockingInputSecondaryAction,
  AgentBlockingInputSubmission,
} from '@studio/components/agents/AgentBlockingInput/types';
import { SAMPLE_EVAL_CONFIG_PATH } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import { render } from '@testing-library/react';

interface CapturedFilesetProps {
  readonly onSecondaryAction?: () => Promise<void> | void;
  readonly secondaryActions?: readonly AgentBlockingInputSecondaryAction[];
}

const captured: { props: CapturedFilesetProps | null } = { props: null };

vi.mock('@studio/components/agents/AgentBlockingInput/FilesetFileBlockingInput', () => ({
  FilesetFileBlockingInput: (props: CapturedFilesetProps) => {
    captured.props = props;
    return <div data-testid="fileset-file-blocking-input" />;
  },
}));

const request: AgentBlockingInputRequest = {
  id: 'request-1',
  title: 'Select an evaluation config',
};

beforeEach(() => {
  captured.props = null;
});

describe('EvalConfigBlockingInput', () => {
  it('emits a sample-config payload that includes the agent and its eval fileset', async () => {
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();

    render(
      <EvalConfigBlockingInput
        input={{ agent: 'react-agent' }}
        request={request}
        workspace="default"
        onSubmit={onSubmit}
      />
    );

    const sampleAction = captured.props?.secondaryActions?.find(
      (action) => action.label === 'Use sample config'
    );
    expect(sampleAction).toBeDefined();
    expect(sampleAction?.disabled).toBe(false);

    await sampleAction?.onClick();

    expect(onSubmit).toHaveBeenCalledWith({
      displayText: 'Use sample evaluation config',
      value: {
        use_sample_eval_config: true,
        agent: 'react-agent',
        eval_config: SAMPLE_EVAL_CONFIG_PATH,
        eval_config_fileset: 'react-agent-eval',
      },
    });
  });

  it('falls back to default_agent when no agent is supplied', async () => {
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();

    render(
      <EvalConfigBlockingInput
        input={{ default_agent: 'tool-agent' }}
        request={request}
        workspace="default"
        onSubmit={onSubmit}
      />
    );

    const sampleAction = captured.props?.secondaryActions?.find(
      (action) => action.label === 'Use sample config'
    );
    await sampleAction?.onClick();

    expect(onSubmit).toHaveBeenCalledWith({
      displayText: 'Use sample evaluation config',
      value: {
        use_sample_eval_config: true,
        agent: 'tool-agent',
        eval_config: SAMPLE_EVAL_CONFIG_PATH,
        eval_config_fileset: 'tool-agent-eval',
      },
    });
  });

  it('disables the sample-config action and omits agent fields when no agent is known', async () => {
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();

    render(
      <EvalConfigBlockingInput
        input={{}}
        request={request}
        workspace="default"
        onSubmit={onSubmit}
      />
    );

    const sampleAction = captured.props?.secondaryActions?.find(
      (action) => action.label === 'Use sample config'
    );
    expect(sampleAction?.disabled).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('emits a needs_eval_config payload from the "I don\'t have a config" secondary action', async () => {
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();

    render(
      <EvalConfigBlockingInput
        input={{ agent: 'react-agent' }}
        request={request}
        workspace="default"
        onSubmit={onSubmit}
      />
    );

    await captured.props?.onSecondaryAction?.();

    expect(onSubmit).toHaveBeenCalledWith({
      displayText: "I don't have an evaluation config yet",
      value: { needs_eval_config: true },
    });
  });
});
