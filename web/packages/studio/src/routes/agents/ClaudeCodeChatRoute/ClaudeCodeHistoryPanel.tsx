// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, SegmentedControl, Tooltip } from '@nvidia/foundations-react-core';
import { ClaudeCodeArtifactsPane } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/ClaudeCodeArtifactsPane';
import { PANEL_TAB_ITEMS } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/constants';
import { isClaudeCodePanelTab } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import { HistoryPanelContents } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/HistoryPanelContents';
import { SkillsPanelContents } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/SkillsPanelContents';
import type { ClaudeCodeHistoryPanelProps } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/types';
import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { CLAUDE_CODE_HISTORY_OPEN_KEY, CLAUDE_CODE_PANEL_TAB_KEY } from '@studio/util/localStorage';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { type FC } from 'react';

export const ClaudeCodeHistoryPanel: FC<ClaudeCodeHistoryPanelProps> = ({
  hideArtifacts,
  ...props
}) => {
  const [historyOpen, setHistoryOpen] = useLocalStorage(CLAUDE_CODE_HISTORY_OPEN_KEY, 'true');
  const [panelTab, setPanelTab] = useLocalStorage(CLAUDE_CODE_PANEL_TAB_KEY, 'history');
  const isOpen = historyOpen !== 'false';
  const selectedTab =
    typeof panelTab === 'string' && isClaudeCodePanelTab(panelTab) ? panelTab : 'history';
  const toggleLabel = isOpen ? 'Collapse Claude history' : 'Expand Claude history';
  const handleTabChange = (value: string) => {
    if (isClaudeCodePanelTab(value)) setPanelTab(value);
  };

  if (!isOpen) {
    return (
      <aside className="flex shrink-0 justify-center border-t border-base bg-surface-base p-density-xs lg:w-14 lg:border-l lg:border-t-0">
        <Tooltip slotContent={toggleLabel} side="left">
          <Button
            aria-label={toggleLabel}
            kind="tertiary"
            size="small"
            type="button"
            onClick={() => setHistoryOpen('true')}
          >
            <PanelRightOpen size={18} />
          </Button>
        </Tooltip>
      </aside>
    );
  }

  return (
    <aside className="flex min-h-80 w-full shrink-0 flex-col border-t border-base bg-surface-base lg:w-[30rem] lg:border-l lg:border-t-0 xl:w-[32rem]">
      {!hideArtifacts && (
        <ClaudeCodeArtifactsPane
          artifacts={props.artifacts}
          collapseLabel={toggleLabel}
          onCollapse={() => setHistoryOpen('false')}
        />
      )}
      <section className={`flex min-h-0 flex-col ${hideArtifacts ? 'flex-1' : 'basis-1/2'}`}>
        <Flex
          align="center"
          justify="between"
          gap="density-sm"
          className="border-b border-base px-density-md py-density-sm"
        >
          <SegmentedControl
            size="tiny"
            value={selectedTab}
            onValueChange={handleTabChange}
            items={PANEL_TAB_ITEMS}
            className="min-w-0 flex-1"
          />
          {hideArtifacts && (
            <Tooltip slotContent={toggleLabel} side="left">
              <Button
                aria-label={toggleLabel}
                kind="tertiary"
                size="small"
                type="button"
                onClick={() => setHistoryOpen('false')}
              >
                <PanelRightClose size={18} />
              </Button>
            </Tooltip>
          )}
        </Flex>
        <div className="flex min-h-0 flex-1 flex-col">
          {selectedTab === 'history' ? (
            <HistoryPanelContents {...props} />
          ) : (
            <SkillsPanelContents />
          )}
        </div>
      </section>
    </aside>
  );
};
