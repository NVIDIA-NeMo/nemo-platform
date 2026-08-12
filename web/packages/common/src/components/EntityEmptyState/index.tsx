// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ENTITY_EMPTY_STATES,
  type EntityKey,
} from '@nemo/common/src/components/EntityEmptyState/registry';
import { useCopyToClipboard } from '@nemo/common/src/hooks/useCopyToClipboard';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Button, Flex, StatusMessage, Stack, Text } from '@nvidia/foundations-react-core';
import { Copy, TriangleAlert } from 'lucide-react';
import { type FC, useCallback } from 'react';
import { useNavigate } from 'react-router';

/** The three governed empty-state variants. */
export type EntityEmptyStateVariant = 'first-use' | 'no-results' | 'error';

export interface EntityEmptyStateProps {
  entity: EntityKey;
  variant: EntityEmptyStateVariant;
  /**
   * Overrides the registry create action's handler (e.g. opens a create modal).
   * When omitted, a `createAction.to` route is navigated to instead.
   * `first-use` only.
   */
  onCreate?: () => void;
  /** Clears the active filters/search. `no-results` only. */
  onClearFilters?: () => void;
  /** Re-runs the failed request. `error` only. */
  onRetry?: () => void;
  className?: string;
}

/**
 * The single canonical empty state for Studio lists, tables, and panels. Copy,
 * iconography, CLI command, and skill prompt come from the entity registry; the
 * variant selects which affordances render. See the `ui-design` skill's
 * `empty-states` reference.
 */
export const EntityEmptyState: FC<EntityEmptyStateProps> = ({
  entity,
  variant,
  onCreate,
  onClearFilters,
  onRetry,
  className,
}) => {
  const descriptor = ENTITY_EMPTY_STATES[entity];
  const navigate = useNavigate();

  if (variant === 'no-results') {
    return (
      <Centered className={className} testId="entity-empty-state-no-results">
        <StatusMessage
          slotHeading="No results found"
          slotSubheading="No items match your current search or filters."
          slotFooter={
            onClearFilters ? (
              <Button kind="tertiary" onClick={onClearFilters}>
                Clear filters
              </Button>
            ) : null
          }
        />
      </Centered>
    );
  }

  if (variant === 'error') {
    return (
      <Centered className={className} testId="entity-empty-state-error">
        <StatusMessage
          slotMedia={<TriangleAlert className="size-12 text-feedback-danger" />}
          slotHeading="Something went wrong"
          slotSubheading="We couldn't load this list. Please try again."
          slotFooter={
            onRetry ? (
              <Button color="brand" onClick={onRetry}>
                Try again
              </Button>
            ) : null
          }
        />
      </Centered>
    );
  }

  const { icon: Icon, heading, subheading, createAction, cliCommand, skillPrompt } = descriptor;
  const handleCreate =
    onCreate ?? (createAction?.to ? () => navigate(createAction.to as string) : undefined);

  return (
    <Centered className={className} testId="entity-empty-state-first-use">
      <StatusMessage
        slotMedia={<Icon className="size-12" />}
        slotHeading={heading}
        slotSubheading={subheading}
        slotFooter={
          createAction && handleCreate ? (
            <Button color="brand" onClick={handleCreate}>
              {createAction.label}
            </Button>
          ) : null
        }
      />
      {(cliCommand || skillPrompt) && (
        <Stack gap="density-sm" className="mt-density-lg w-full max-w-[28rem]">
          {cliCommand && (
            <CopyRow label="Prefer the CLI?" value={cliCommand} copyLabel="Copy CLI command" />
          )}
          {skillPrompt && (
            <CopyRow label="Ask an agent" value={skillPrompt} copyLabel="Copy agent prompt" />
          )}
        </Stack>
      )}
    </Centered>
  );
};

const Centered: FC<{ children: React.ReactNode; className?: string; testId: string }> = ({
  children,
  className,
  testId,
}) => (
  <Flex
    direction="col"
    align="center"
    justify="center"
    className={`h-full w-full ${className ?? ''}`}
    data-testid={testId}
  >
    {children}
  </Flex>
);

/**
 * A compact, copy-to-clipboard row: a small label, a monospace snippet, and a
 * copy button. Kept out of the StatusMessage footer so the ≤2-action rule for
 * empty states holds.
 */
const CopyRow: FC<{ label: string; value: string; copyLabel: string }> = ({
  label,
  value,
  copyLabel,
}) => {
  const toast = useToast();
  const { copyToClipboard } = useCopyToClipboard({
    onSuccess: () => toast.success('Copied to clipboard'),
    onError: () => toast.error('Failed to copy to clipboard'),
  });
  const handleCopy = useCallback(() => void copyToClipboard(value), [copyToClipboard, value]);

  return (
    <Flex align="center" justify="between" gap="density-sm" className="rounded border p-density-sm">
      <Stack gap="density-xxs" className="min-w-0">
        <Text kind="label/bold/xs" className="text-secondary">
          {label}
        </Text>
        <code className="truncate font-mono text-sm text-text-primary">{value}</code>
      </Stack>
      <Button kind="tertiary" size="tiny" aria-label={copyLabel} onClick={handleCopy}>
        <Copy />
      </Button>
    </Flex>
  );
};
