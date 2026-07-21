// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { entitiesGetEntityById } from '@nemo/sdk/generated/platform/api';
import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  executeGuardrailCheck,
  resolveConfigModel,
} from '@studio/api/guardrail-checks/guardrailChecks';
import { useUpdateGuardrailCheck } from '@studio/api/guardrail-checks/hooks';
import type {
  GuardrailCheckEntity,
  GuardrailCheckMessage,
} from '@studio/api/guardrail-checks/types';
import { GuardrailMessageRow } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailMessageRow';
import { Plus } from 'lucide-react';
import { type FC, useCallback, useEffect, useRef, useState } from 'react';

interface GuardrailTestCardProps {
  check: GuardrailCheckEntity;
  index: number;
  workspace: string;
}

type ViewMode = 'chat' | 'json';

const DEFAULT_MESSAGE: GuardrailCheckMessage = { role: 'user', content: '' };

export const GuardrailTestCard: FC<GuardrailTestCardProps> = ({ check, index, workspace }) => {
  const toast = useToast();
  const [messages, setMessages] = useState<GuardrailCheckMessage[]>(() => check.data.messages);
  const [viewMode, setViewMode] = useState<ViewMode>('chat');
  const [isGenerating, setIsGenerating] = useState(false);

  // Sync local draft if the server entity is refreshed externally
  const lastCheckId = useRef(check.id);
  useEffect(() => {
    if (check.id !== lastCheckId.current) {
      lastCheckId.current = check.id;
      setMessages(check.data.messages);
    }
  }, [check.id, check.data.messages]);

  const updateMutation = useUpdateGuardrailCheck({
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to save check'));
    },
  });

  const persist = useCallback(
    (nextMessages: GuardrailCheckMessage[]) => {
      updateMutation.mutate({
        workspace,
        name: check.name,
        patch: {
          data: { ...check.data, messages: nextMessages },
          expected_db_version: check.db_version,
          parent: check.parent,
        },
      });
    },
    [updateMutation, workspace, check]
  );

  const handleChange = (i: number, updated: GuardrailCheckMessage) => {
    setMessages((prev) => prev.map((m, idx) => (idx === i ? updated : m)));
  };

  const handleMoveUp = (i: number) => {
    if (i === 0) return;
    setMessages((prev) => {
      const next = [...prev];
      [next[i - 1], next[i]] = [next[i], next[i - 1]];
      persist(next);
      return next;
    });
  };

  const handleMoveDown = (i: number) => {
    setMessages((prev) => {
      if (i >= prev.length - 1) return prev;
      const next = [...prev];
      [next[i], next[i + 1]] = [next[i + 1], next[i]];
      persist(next);
      return next;
    });
  };

  const handleCopy = (i: number) => {
    const content = messages[i]?.content;
    const text = typeof content === 'string' ? content : JSON.stringify(content);
    navigator.clipboard.writeText(text).catch(() => {
      toast.error('Failed to copy to clipboard');
    });
  };

  const handleDelete = (i: number) => {
    setMessages((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      persist(next);
      return next;
    });
  };

  const handleAddMessage = () => {
    setMessages((prev) => {
      const next = [...prev, { ...DEFAULT_MESSAGE }];
      persist(next);
      return next;
    });
  };

  const handleBlur = (currentMessages: GuardrailCheckMessage[]) => {
    persist(currentMessages);
  };

  const handleGenerateResponse = async () => {
    if (!check.parent) {
      toast.error('Cannot generate response: check has no parent config');
      return;
    }
    setIsGenerating(true);
    try {
      const configEntity = await entitiesGetEntityById(check.parent);
      const configData = (configEntity.data as { data?: RailsConfigOutput }).data;
      const model = resolveConfigModel(configData, configEntity.name);
      const response = await executeGuardrailCheck(workspace, {
        model,
        messages,
        guardrails: check.data.guardrails ?? { config_ids: [configEntity.name] },
      });
      const statusText = response.status === 'success' ? 'Allowed' : 'Guarded';
      const assistantMsg: GuardrailCheckMessage = {
        role: 'assistant',
        content: `[${statusText} by guardrails]`,
      };
      setMessages((prev) => {
        const next = [...prev, assistantMsg];
        persist(next);
        return next;
      });
    } catch (err) {
      toast.error(
        getErrorMessage(
          err instanceof Error ? err : new Error(String(err)),
          'Failed to generate response'
        )
      );
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Stack
      gap="density-md"
      className="rounded-md border border-border-subtle bg-surface-raised p-density-lg"
    >
      {/* Card header */}
      <Flex align="center" justify="between">
        <Text kind="label/bold/md">Test {index + 1}</Text>
        <Flex gap="density-xs">
          <Button
            kind={viewMode === 'chat' ? 'secondary' : 'tertiary'}
            color="neutral"
            size="small"
            onClick={() => setViewMode('chat')}
          >
            Chat
          </Button>
          <Button
            kind={viewMode === 'json' ? 'secondary' : 'tertiary'}
            color="neutral"
            size="small"
            onClick={() => setViewMode('json')}
          >
            JSON
          </Button>
        </Flex>
      </Flex>

      {/* Chat view */}
      {viewMode === 'chat' ? (
        <Stack gap="density-md">
          {messages.map((msg, i) => (
            <GuardrailMessageRow
              key={i}
              message={msg}
              isFirst={i === 0}
              isLast={i === messages.length - 1}
              isGenerating={isGenerating}
              onChange={(updated) => handleChange(i, updated)}
              onMoveUp={() => handleMoveUp(i)}
              onMoveDown={() => handleMoveDown(i)}
              onCopy={() => handleCopy(i)}
              onDelete={() => handleDelete(i)}
              onGenerateResponse={i === messages.length - 1 ? handleGenerateResponse : undefined}
              onBlur={() => handleBlur(messages)}
            />
          ))}
          <Button
            kind="tertiary"
            color="neutral"
            size="small"
            onClick={handleAddMessage}
            className="w-fit"
          >
            <Plus size={14} />
            Add Message
          </Button>
        </Stack>
      ) : (
        /* JSON view (read-only) */
        <pre className="overflow-auto rounded bg-surface p-density-md text-xs font-mono text-text-primary">
          {JSON.stringify(messages, null, 2)}
        </pre>
      )}
    </Stack>
  );
};
