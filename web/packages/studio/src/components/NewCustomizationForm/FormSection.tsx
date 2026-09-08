// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

interface FormSectionProps {
  title: string;
  description?: ReactNode;
  collapsible?: boolean;
  children: ReactNode;
}

export const FormSection: FC<FormSectionProps> = ({
  title,
  description,
  collapsible = false,
  children,
}) => {
  if (collapsible) {
    return (
      <AccordionRoot multiple>
        <AccordionItem value={title} className="border-b-0">
          <AccordionTrigger>
            <Text kind="body/bold/lg">{title}</Text>
          </AccordionTrigger>
          <AccordionContent>
            <Stack gap="density-md" className="pt-density-md">
              {description && <Text kind="body/regular/md">{description}</Text>}
              {children}
            </Stack>
          </AccordionContent>
        </AccordionItem>
      </AccordionRoot>
    );
  }

  return (
    <Stack gap="density-md">
      <Stack gap="density-sm" className="pb-density-xl">
        <Text kind="body/bold/lg">{title}</Text>
        {description && <Text kind="body/regular/md">{description}</Text>}
      </Stack>
      {children}
    </Stack>
  );
};
