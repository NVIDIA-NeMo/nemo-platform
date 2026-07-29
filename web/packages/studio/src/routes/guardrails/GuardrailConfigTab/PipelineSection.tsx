// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import { Badge, Divider, Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import {
  EmptyText,
  FieldList,
} from '@studio/routes/guardrails/GuardrailConfigTab/configPrimitives';
import { detectorMeta } from '@studio/routes/guardrails/GuardrailConfigTab/detectors';
import { recognizeFlow } from '@studio/routes/guardrails/GuardrailConfigTab/flowRegistry';
import type { Field, StageKey } from '@studio/routes/guardrails/GuardrailConfigTab/types';
import { Waypoints } from 'lucide-react';
import { Fragment, type FC, type ReactNode } from 'react';

interface StageDescriptor {
  key: StageKey;
  title: string;
  caption: string;
  /** Core stages are always shown, even when empty, so gaps are visible. */
  core: boolean;
}

const STAGES: StageDescriptor[] = [
  {
    key: 'input',
    title: 'Input rails',
    caption: 'Applied to the user message before the LLM.',
    core: true,
  },
  {
    key: 'dialog',
    title: 'Dialog rails',
    caption: 'Topical control over the conversation flow.',
    core: false,
  },
  {
    key: 'retrieval',
    title: 'Retrieval rails',
    caption: 'Applied to retrieved knowledge-base chunks (RAG).',
    core: true,
  },
  {
    key: 'output',
    title: 'Output rails',
    caption: 'Applied to the LLM response before it reaches the user.',
    core: true,
  },
  { key: 'tool_input', title: 'Tool-input rails', caption: 'Validate tool inputs.', core: false },
  {
    key: 'tool_output',
    title: 'Tool-output rails',
    caption: 'Validate tool outputs.',
    core: false,
  },
  {
    key: 'actions',
    title: 'Action rails',
    caption: 'Actions that resolve instantly.',
    core: false,
  },
];

const stageFlows = (rails: RailsOutput | undefined, key: StageKey): string[] => {
  switch (key) {
    case 'input':
      return rails?.input?.flows ?? [];
    case 'output':
      return rails?.output?.flows ?? [];
    case 'retrieval':
      return rails?.retrieval?.flows ?? [];
    case 'tool_input':
      return rails?.tool_input?.flows ?? [];
    case 'tool_output':
      return rails?.tool_output?.flows ?? [];
    default:
      return [];
  }
};

const isParallel = (rails: RailsOutput | undefined, key: StageKey): boolean => {
  switch (key) {
    case 'input':
      return rails?.input?.parallel ?? false;
    case 'output':
      return rails?.output?.parallel ?? false;
    case 'tool_input':
      return rails?.tool_input?.parallel ?? false;
    case 'tool_output':
      return rails?.tool_output?.parallel ?? false;
    default:
      return false;
  }
};

/** Stage-specific extra config rendered below the flow list. */
const stageExtras = (rails: RailsOutput | undefined, key: StageKey): Field[] => {
  if (key === 'output') {
    const streaming = rails?.output?.streaming;
    const fields: Field[] = [];
    if (streaming?.enabled != null) {
      fields.push({ label: 'Streaming', value: streaming.enabled ? 'Enabled' : 'Disabled' });
    }
    if (streaming?.chunk_size != null) {
      fields.push({ label: 'Chunk size', value: String(streaming.chunk_size) });
    }
    if (rails?.output?.apply_to_reasoning_traces != null) {
      fields.push({
        label: 'Apply to reasoning traces',
        value: rails.output.apply_to_reasoning_traces ? 'Yes' : 'No',
      });
    }
    return fields;
  }
  if (key === 'dialog') {
    const dialog = rails?.dialog;
    const fields: Field[] = [];
    if (dialog?.single_call?.enabled != null) {
      fields.push({
        label: 'Single call',
        value: dialog.single_call.enabled ? 'Enabled' : 'Disabled',
      });
    }
    if (dialog?.user_messages?.embeddings_only != null) {
      fields.push({
        label: 'Embeddings-only intents',
        value: dialog.user_messages.embeddings_only ? 'Yes' : 'No',
      });
    }
    return fields;
  }
  if (key === 'actions') {
    const actions = rails?.actions?.instant_actions ?? [];
    return actions.length ? [{ label: 'Instant actions', value: actions.join(', ') }] : [];
  }
  return [];
};

const FlowRow: FC<{ flow: string; isFirst: boolean }> = ({ flow, isFirst }) => {
  const recognized = recognizeFlow(flow);
  const showRaw = recognized.recognized && recognized.raw !== recognized.label;
  return (
    <Flex
      role="listitem"
      align="center"
      justify="between"
      gap="density-md"
      className={isFirst ? 'py-density-xs' : 'py-density-xs border-t border-border-subtle'}
    >
      <Stack gap="0" className="min-w-0">
        <Text kind="body/regular/sm" className="truncate" title={recognized.raw}>
          {recognized.label}
        </Text>
        {showRaw ? (
          <Text
            kind="body/regular/xs"
            className="truncate text-text-secondary"
            title={recognized.raw}
          >
            {recognized.raw}
          </Text>
        ) : null}
      </Stack>
      {recognized.detectorKey ? (
        <Badge color="gray" kind="outline">
          {detectorMeta(recognized.detectorKey).label}
        </Badge>
      ) : null}
    </Flex>
  );
};

const StageCard: FC<{ stage: StageDescriptor; rails: RailsOutput | undefined }> = ({
  stage,
  rails,
}) => {
  const flows = stageFlows(rails, stage.key);
  const extras = stageExtras(rails, stage.key);
  const parallel = isParallel(rails, stage.key);
  const badges: ReactNode[] = [];
  if (parallel) {
    badges.push(
      <Badge key="parallel" color="blue" kind="outline">
        Parallel
      </Badge>
    );
  }

  return (
    <Stack gap="density-sm">
      <Flex align="start" justify="between" gap="density-md">
        <Stack gap="0" className="min-w-0">
          <Text kind="label/bold/md">{stage.title}</Text>
          <Text kind="body/regular/xs" className="text-text-secondary">
            {stage.caption}
          </Text>
        </Stack>
        {badges.length ? (
          <Flex align="center" gap="density-xs" wrap="wrap">
            {badges}
          </Flex>
        ) : null}
      </Flex>

      {flows.length ? (
        <Stack gap="0" role="list">
          {flows.map((flow, index) => (
            <FlowRow key={`${flow}-${index}`} flow={flow} isFirst={index === 0} />
          ))}
        </Stack>
      ) : (
        <EmptyText>No rails configured.</EmptyText>
      )}

      <FieldList fields={extras} />
    </Stack>
  );
};

/** True when a non-core stage has any content worth rendering. */
const stageHasContent = (rails: RailsOutput | undefined, key: StageKey): boolean =>
  stageFlows(rails, key).length > 0 || stageExtras(rails, key).length > 0;

export const PipelineSection: FC<{ rails: RailsOutput | undefined }> = ({ rails }) => {
  const stages = STAGES.filter((stage) => stage.core || stageHasContent(rails, stage.key));
  return (
    <Panel slotHeading="Pipeline" slotIcon={<Waypoints />} elevation="high" density="compact">
      <Stack gap="density-lg">
        {stages.map((stage, index) => (
          <Fragment key={stage.key}>
            {index > 0 ? <Divider /> : null}
            <StageCard stage={stage} rails={rails} />
          </Fragment>
        ))}
      </Stack>
    </Panel>
  );
};
