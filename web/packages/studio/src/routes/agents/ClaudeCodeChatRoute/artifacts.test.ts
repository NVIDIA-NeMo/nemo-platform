// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  createEmptyClaudeCodeChatArtifacts,
  updateClaudeCodeChatArtifactsFromEvent,
  updateClaudeCodeChatArtifactsFromHistoryItems,
  updateClaudeCodeChatArtifactsFromSelections,
} from '@studio/routes/agents/ClaudeCodeChatRoute/artifacts';

describe('Claude Code chat artifacts', () => {
  it('keeps the latest streamed coding-agent model', () => {
    const initial = createEmptyClaudeCodeChatArtifacts();
    const first = updateClaudeCodeChatArtifactsFromEvent(initial, {
      type: 'assistant',
      message: { model: 'claude-sonnet-4-5', content: [] },
    });
    const updated = updateClaudeCodeChatArtifactsFromEvent(first, {
      type: 'assistant',
      message: { model: 'claude-sonnet-4-6', content: [] },
    });

    expect(updated.model).toBeUndefined();
    expect(updated.model_source).toBeUndefined();
    expect(updated.coding_agent_model).toBe('claude-sonnet-4-6');
  });

  it('promotes agent and selected model answers while preserving coding-agent model', () => {
    const withCodingModel = updateClaudeCodeChatArtifactsFromEvent(
      createEmptyClaudeCodeChatArtifacts(),
      {
        type: 'assistant',
        message: { model: 'claude-sonnet-4-6', content: [] },
      }
    );

    const withSelections = updateClaudeCodeChatArtifactsFromSelections(
      withCodingModel,
      [
        { header: 'Agent', question: 'Which agent should be used?' },
        { header: 'Model', question: 'Which inference provider and model should be used?' },
        { header: 'Dataset type', question: 'What kind of dataset do you want to generate?' },
      ],
      {
        'Which agent should be used?': 'beach-finder',
        'Which inference provider and model should be used?':
          'nvidia-build - meta/llama-3.3-70b-instruct',
        'What kind of dataset do you want to generate?': 'Text classification',
      }
    );

    expect(withSelections.agent).toBe('beach-finder');
    expect(withSelections.model).toBe('nvidia-build - meta/llama-3.3-70b-instruct');
    expect(withSelections.model_source).toBe('selection');
    expect(withSelections.coding_agent_model).toBe('claude-sonnet-4-6');
    expect(withSelections.selections).toEqual([
      { label: 'Agent', value: 'beach-finder' },
      { label: 'Model', value: 'nvidia-build - meta/llama-3.3-70b-instruct' },
      { label: 'Dataset', value: 'Text classification' },
    ]);
  });

  it('collects relevant tool artifacts from streamed events', () => {
    const artifacts = updateClaudeCodeChatArtifactsFromEvent(
      { ...createEmptyClaudeCodeChatArtifacts(), workspace: 'default' },
      {
        type: 'assistant',
        message: {
          content: [
            {
              type: 'tool_use',
              name: 'Write',
              input: { file_path: 'agents/beach-finder.yml' },
            },
            {
              type: 'tool_use',
              name: 'mcp__nemo_studio__studio_link',
              input: { destination: 'agents', label: 'Agents' },
            },
            {
              type: 'tool_use',
              name: 'mcp__nemo_studio__job_progress',
              input: {
                job_name: 'agent-eval-1',
                job_type: 'agent_evaluation',
                source: 'evaluator',
              },
            },
          ],
        },
      }
    );

    expect(artifacts.files).toEqual([{ action: 'Wrote', path: 'agents/beach-finder.yml' }]);
    expect(artifacts.links).toEqual([
      { label: 'Agents', destination: 'agents', href: '/workspaces/default/agents' },
    ]);
    expect(artifacts.jobs).toEqual([
      {
        name: 'agent-eval-1',
        job_type: 'agent_evaluation',
        source: 'evaluator',
        href: '/workspaces/default/agents/evaluations/agent-eval-1',
      },
    ]);
    expect(artifacts.tools).toEqual([
      'Write',
      'mcp__nemo_studio__studio_link',
      'mcp__nemo_studio__job_progress',
    ]);
  });

  it('does not double encode encoded file paths in studio link artifacts', () => {
    const artifacts = updateClaudeCodeChatArtifactsFromEvent(
      { ...createEmptyClaudeCodeChatArtifacts(), workspace: 'default' },
      {
        type: 'assistant',
        message: {
          content: [
            {
              type: 'tool_use',
              name: 'mcp__nemo_studio__studio_link',
              input: {
                destination: 'fileset_file',
                name: 'training data',
                file_path_encoded: 'nested%2Fexamples.jsonl',
                label: 'Dataset file',
              },
            },
          ],
        },
      }
    );

    expect(artifacts.links).toEqual([
      {
        label: 'Dataset file',
        destination: 'fileset_file',
        href: '/workspaces/default/filesets/training%20data/file/nested%2Fexamples.jsonl',
      },
    ]);
  });

  it('promotes draft spec name and model over the coding-agent model', () => {
    const withCodingModel = updateClaudeCodeChatArtifactsFromEvent(
      createEmptyClaudeCodeChatArtifacts(),
      {
        type: 'assistant',
        message: { model: 'claude-sonnet-4-6', content: [] },
      }
    );

    const withSpecModel = updateClaudeCodeChatArtifactsFromEvent(withCodingModel, {
      type: 'assistant',
      message: {
        content: [
          {
            type: 'text',
            text: [
              'Draft Spec: `cat-identifier`',
              'Name: `cat-identifier`',
              '',
              'Model',
              '`cloud, nvidia/llama-3.3-nemotron-super-49b-v1` - default, good reasoning',
              '',
              'Framework',
              'langgraph-nat',
            ].join('\n'),
          },
        ],
      },
    });
    const afterCodeModelUpdate = updateClaudeCodeChatArtifactsFromEvent(withSpecModel, {
      type: 'assistant',
      message: { model: 'claude-opus-4-6', content: [] },
    });

    expect(afterCodeModelUpdate.agent).toBe('cat-identifier');
    expect(afterCodeModelUpdate.model).toBe('cloud, nvidia/llama-3.3-nemotron-super-49b-v1');
    expect(afterCodeModelUpdate.model_source).toBe('spec');
    expect(afterCodeModelUpdate.coding_agent_model).toBe('claude-opus-4-6');
  });

  it('derives spec artifacts from loaded transcript items', () => {
    const artifacts = updateClaudeCodeChatArtifactsFromHistoryItems(
      createEmptyClaudeCodeChatArtifacts(),
      [
        { kind: 'user', text: 'draft a cat identifier' },
        {
          kind: 'assistant',
          parts: [
            {
              type: 'text',
              text: [
                'Name: `cat-identifier`',
                '',
                'Model',
                '`cloud, nvidia/llama-3.3-nemotron-super-49b-v1`',
              ].join('\n'),
            },
          ],
        },
      ]
    );

    expect(artifacts.agent).toBe('cat-identifier');
    expect(artifacts.model).toBe('cloud, nvidia/llama-3.3-nemotron-super-49b-v1');
    expect(artifacts.model_source).toBe('spec');
  });
});
