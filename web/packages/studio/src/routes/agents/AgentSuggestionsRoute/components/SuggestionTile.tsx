// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Block, Button, Card, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { featureFlags } from '@studio/constants/featureFlags';
import { BeforeAfterComparison } from '@studio/routes/agents/AgentSuggestionsRoute/components/BeforeAfterComparison';
import {
  EVAL_STATUS_COLOR,
  EVAL_STATUS_LABEL,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type { SuggestionTileProps } from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { formatActions, severityColor } from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { Check, FlaskConical } from 'lucide-react';
import { type FC, memo } from 'react';
import { Link } from 'react-router-dom';

export const SuggestionTile: FC<SuggestionTileProps> = memo(
  ({ suggestion, onApply, isApplying, isApplied: isAppliedProp, applyError, evalState }) => {
    // Persisted flag wins; prop covers the gap before refetched JSONL arrives.
    const isApplied = suggestion.applied === true || !!isAppliedProp;
    const canApply = !!suggestion.apply && !!onApply;
    const actions = suggestion.suggested_actions ?? [];
    const severity = suggestion.severity ?? 'low';
    // Render the side-by-side view once a baseline ("before") run exists and the
    // flag is on; otherwise fall back to the optimized-only score badges.
    const showComparison = featureFlags.optimizerComparisonEnabled && !!evalState?.baseline;

    return (
      <Card>
        <Block className="flow-root">
          {canApply && (
            <Button
              kind="secondary"
              size="small"
              disabled={isApplying || isApplied}
              onClick={() => onApply?.(suggestion)}
              aria-label={`Apply suggestion: ${suggestion.title}`}
              className="float-right ml-density-xl mb-density-sm"
            >
              {isApplied && !isApplying ? (
                <>
                  <Check size={14} /> Applied
                </>
              ) : isApplying ? (
                'Applying…'
              ) : (
                'Apply Suggestion'
              )}
            </Button>
          )}
          <Flex align="center" gap="density-sm" wrap="wrap">
            <Text kind="body/bold/md">{suggestion.title}</Text>
            <Badge kind="outline" color={severityColor(severity)}>
              {severity.toUpperCase()}
            </Badge>
          </Flex>
          {suggestion.detail && (
            <Block className="mt-density-sm">
              <Text kind="body/regular/sm" color="secondary">
                {suggestion.detail}
              </Text>
            </Block>
          )}
          {actions.length > 0 && (
            <Block className="bg-surface-sunken rounded-md p-density-md -ml-density-sm mt-density-sm">
              <Text kind="body/regular/sm" color="secondary">
                <Text kind="body/bold/sm">Suggested Actions: </Text>
                {formatActions(actions)}
              </Text>
            </Block>
          )}
          {suggestion.apply_description && (
            <Block className="mt-density-sm">
              <Text kind="body/regular/sm" color="secondary">
                {suggestion.apply_description}
              </Text>
            </Block>
          )}
        </Block>

        {applyError && (
          <Text kind="body/regular/sm" color="danger" className="mt-density-sm block">
            {applyError}
          </Text>
        )}

        {evalState && (
          <Stack gap="density-xs" data-testid="suggestion-tile-eval-row" className="mt-density-sm">
            <Flex align="center" gap="density-sm" wrap="wrap">
              <FlaskConical size={14} />
              <Text kind="body/bold/sm">Evaluation</Text>
              <Badge kind="outline" color={EVAL_STATUS_COLOR[evalState.status]}>
                {EVAL_STATUS_LABEL[evalState.status]}
              </Badge>
              <Link to={evalState.detailHref} className="text-xs">
                View details
              </Link>
            </Flex>
            {showComparison ? (
              <BeforeAfterComparison evalState={evalState} />
            ) : (
              <>
                {evalState.status === 'completed' && evalState.scores.length > 0 && (
                  <Flex gap="density-md" wrap="wrap">
                    {evalState.scores.map((s) => (
                      <Badge key={s.evaluator} kind="solid" color="green">
                        {s.evaluator}: {s.averageScore.toFixed(2)}
                      </Badge>
                    ))}
                  </Flex>
                )}
                {evalState.status === 'completed' && evalState.scores.length === 0 && (
                  <Text kind="body/regular/sm" color="secondary">
                    Eval finished — no evaluator scores parsed from the output fileset.
                  </Text>
                )}
                {evalState.error && (
                  <Text kind="body/regular/sm" color="danger">
                    {evalState.error}
                  </Text>
                )}
              </>
            )}
          </Stack>
        )}
      </Card>
    );
  }
);
