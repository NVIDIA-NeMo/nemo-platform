// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { Dropdown, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { EllipsisVertical, Trash } from 'lucide-react';
import { FC, ReactNode } from 'react';

interface EventListItemLayoutProps {
  /** Icon to display in the timeline circle */
  icon: ReactNode;
  /** Content for the header row (actor name, action text, etc.) */
  slotHeader: ReactNode;
  /** ISO timestamp for the event */
  timestamp?: string;
  /** Whether this is the last item in the list (hides the connecting line) */
  isLast: boolean;
  /** Callback when delete action is triggered */
  onDelete?: () => void;
  /** Content slot for event-specific rendering */
  children: ReactNode;
  /** Test ID suffix for the container */
  testIdSuffix?: string;
}

/**
 * Shared layout component for timeline events.
 * Renders the timeline structure (icon circle, connecting line) and header row.
 * Event-specific content is passed via children.
 */
export const EventListItemLayout: FC<EventListItemLayoutProps> = ({
  icon,
  slotHeader,
  timestamp,
  isLast,
  onDelete,
  children,
  testIdSuffix,
}) => {
  return (
    <Flex gap="6" className="w-full" data-testid={`activity-feed-item-${testIdSuffix ?? 'event'}`}>
      {/* Timeline column - self-stretch ensures it fills the full height including content padding */}
      <div className="flex flex-col items-center w-8 shrink-0 self-stretch">
        {/* Icon circle */}
        <div className="flex items-center justify-center p-2 rounded-full bg-gray-700">{icon}</div>
        {/* Connecting line */}
        {!isLast && (
          <div
            className="flex-1 w-[2px] bg-gray-700 min-h-[24px]"
            data-testid={`activity-feed-item-${testIdSuffix ?? 'event'}-connecting-line`}
          />
        )}
      </div>

      {/* Content column */}
      <Stack gap="density-xs" className="flex-1 pb-6">
        {/* Header row - h-8 matches the icon circle height (32px) for alignment */}
        <Flex align="center" className="w-full h-8">
          {/* Left side: header content from consumer */}
          <Flex gap="density-xs" align="center" wrap="wrap" className="flex-1">
            {slotHeader}
          </Flex>

          {/* Right side: timestamp + menu */}
          <Flex gap="density-sm" align="center" className="shrink-0">
            {timestamp && (
              <Text color="secondary" className="text-right">
                <RelativeTime datetime={timestamp} />
              </Text>
            )}

            {/* Overflow menu */}
            {onDelete && (
              <Dropdown
                items={[
                  {
                    children: 'Delete Annotation',
                    slotStart: <Trash size="16" />,
                    onSelect: onDelete,
                    danger: true,
                  },
                ]}
                align="end"
                showChevron={false}
              >
                <EllipsisVertical size="16" aria-label="Event actions" />
              </Dropdown>
            )}
          </Flex>
        </Flex>

        {/* Content slot - only rendered if there's content */}
        {children && (
          <div
            className="bg-gray-900 rounded-lg p-3 w-full"
            data-testid={`activity-feed-item-${testIdSuffix ?? 'event'}-content`}
          >
            {children}
          </div>
        )}
      </Stack>
    </Flex>
  );
};
