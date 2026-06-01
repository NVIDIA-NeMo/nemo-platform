// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Accordion, AccordionItem, AccordionTrigger } from '@nvidia/foundations-react-core';
import { ComponentProps, FC } from 'react';

type Props = {
  attributes?: {
    Accordion?: ComponentProps<typeof Accordion>;
    AccordionItem?: ComponentProps<typeof AccordionItem>;
    AccordionTrigger?: ComponentProps<typeof AccordionTrigger>;
  };
  slotTrigger: React.ReactNode;
  slotContent: React.ReactNode;
  value: string;
};

/**
 * A visual component that appends a Panel's slotFooter with an Accordion.
 */
export const PanelFooterAccordion: FC<Props> = ({
  attributes,
  slotTrigger,
  slotContent,
  value,
}) => (
  <Accordion
    className="w-full"
    items={[
      {
        attributes: {
          AccordionItem: {
            className: 'border-b-none border-t-1 border-t-base',
            ...attributes?.AccordionItem,
          },
          AccordionTrigger: {
            className: '[&[data-state="closed"]]:rounded-b-density-xl',
            ...attributes?.AccordionTrigger,
          },
        },
        chevronPosition: 'start',
        slotTrigger,
        slotContent,
        value,
      },
    ]}
    {...attributes?.Accordion}
  />
);
