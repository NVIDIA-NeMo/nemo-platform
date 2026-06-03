/*
 * SPDX-FileCopyrightText: Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */
import { isDefined } from '@nemo/common/src/utils/isDefined';
import { Card, Flex, RadioGroupInput, RadioGroupItem, Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { ComponentProps, FC, ReactNode } from 'react';

export interface RadioCardProps extends Omit<ComponentProps<typeof RadioGroupItem>, 'children'> {
  /** The radio value (forwarded to RadioGroupInput) */
  value: string;
  /** Primary label (e.g. "Radio Label") */
  label: ReactNode;
  /** Optional secondary description text */
  description?: ReactNode;
  /** Optional icon or element shown between the radio indicator and the label */
  icon?: ReactNode;
  /** Id for the label element (used for aria-labelledby). Defaults to `${value}-label` */
  labelId?: string;
  /** Which side of the card the radio input renders on. @default "right" */
  labelSide?: 'left' | 'right';
  /** When true, shows the card as selected. When used inside RadioGroupRoot, the group's value controls this; pass checked so the card reflects the active state (e.g. checked={value === 'this-option'}). */
  checked?: boolean;
  /** Whether the underlying radio input is disabled */
  disabled?: boolean;
  /** Additional attributes to pass to the Panel or RadioGroupItem components */
  attributes?: {
    Card?: Partial<ComponentProps<typeof Card>>;
    RadioGroupItem?: Partial<ComponentProps<typeof RadioGroupItem>>;
    RadioGroupInput?: Partial<ComponentProps<typeof RadioGroupInput>>;
  };
}

/**
 * A card-style radio option with optional icon, primary label, and description.
 * Use inside RadioGroupRoot for single-selection from a list of options.
 *
 * @example
 * <RadioGroupRoot value={value} onValueChange={setValue}>
 *   <RadioCard value="a" label="Option A" description="First option" icon={<Cube />} />
 *   <RadioCard value="b" label="Option B" description="Second option" />
 * </RadioGroupRoot>
 */
export const RadioCard: FC<RadioCardProps> = ({
  label,
  description,
  icon,
  value,
  labelId,
  labelSide = 'right',
  checked,
  disabled,
  className,
  attributes = {},
}) => {
  const id = labelId ?? `${String(value).replace(/\s+/g, '-')}-label`;
  const hasDescription = isDefined(description);

  const textStartClass = 'text-left ' + (labelSide === 'right' ? 'col-start-2' : 'col-start-1');
  const labelClass = `${textStartClass} row-start-1`;
  const descriptionClass = `${textStartClass} row-start-2`;

  const colClass =
    labelSide === 'right'
      ? '[&_.nv-card-content]:grid-cols-[auto_1fr]'
      : '[&_.nv-card-content]:grid-cols-[1fr_auto]';
  const inputClass =
    labelSide === 'right'
      ? '[&_.nv-radio-group-input]:col-start-1'
      : '[&_.nv-radio-group-input]:col-start-2';
  const gapClass = hasDescription
    ? '[&_.nv-card-content]:gap-2!'
    : '[&_.nv-card-content]:gap-0! [&_.nv-card-content]:gap-x-2!';
  const nvPanelContentClass = `[&_.nv-card-content]:grid ${colClass} [&_.nv-card-content]:grid-rows-[auto_auto] [&_.nv-card-content]:items-center! [&_.nv-card-content]:w-full ${inputClass} ${gapClass} ${hasDescription ? '[&_.nv-card-content]:row-gap-2' : ''}`;

  return (
    <RadioGroupItem
      aria-labelledby={id}
      className="w-full items-start"
      asChild
      {...attributes?.RadioGroupItem}
    >
      <Card
        className={cn(
          'cursor-pointer [&_*]:cursor-pointer',
          'hover:bg-interaction-hover',
          'data-[state=checked]:border-interaction-selected',
          checked === true && 'border-interaction-selected',
          'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
          nvPanelContentClass,
          className
        )}
        {...attributes?.Card}
      >
        <RadioGroupInput
          value={value}
          disabled={disabled}
          aria-labelledby={id}
          {...attributes?.RadioGroupInput}
        />
        {/* Single column for label + description (separate from the radio indicator column) */}
        <Flex direction="col" gap="density-sm" className={labelClass}>
          <Flex gap="density-md" align="center" className="min-h-0">
            {icon != null && (
              <Flex align="center" className="shrink-0 text-base-foreground" aria-hidden>
                {icon}
              </Flex>
            )}
            <Text kind="body/bold/lg" id={id}>
              {label}
            </Text>
          </Flex>
        </Flex>
        {hasDescription && (
          <Text kind="body/regular/md" color="secondary" className={descriptionClass}>
            {description}
          </Text>
        )}
      </Card>
    </RadioGroupItem>
  );
};
