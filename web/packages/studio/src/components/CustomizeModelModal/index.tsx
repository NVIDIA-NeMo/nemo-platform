// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RadioCard } from '@nemo/common/src/components/RadioCard';
import {
  Banner,
  Button,
  Flex,
  ModalContent,
  ModalDialog,
  ModalFooter,
  ModalHeading,
  ModalMain,
  ModalRoot,
  RadioGroupRoot,
  Stack,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import {
  CUSTOMIZATION_METHODS,
  CustomizationMethod,
} from '@studio/components/CustomizeModelModal/constants';
import { getNewCustomizationJobRoute, getPromptTuningFormRoute } from '@studio/routes/utils';
import { FC, useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface CustomizeModelModalProps {
  open: boolean;
  onClose: () => void;
  workspace: string;
  canFineTune?: boolean;
  canPromptTune?: boolean;
  modelRef?: string;
}

export const CustomizeModelModal: FC<CustomizeModelModalProps> = ({
  open,
  onClose,
  workspace,
  canFineTune = true,
  canPromptTune = true,
  modelRef,
}) => {
  const navigate = useNavigate();
  const [selectedMethod, setSelectedMethod] = useState<CustomizationMethod>(
    canFineTune ? 'fine-tuned' : 'prompt-tuned'
  );

  const canCustomize = canFineTune || canPromptTune;
  const isMethodDisabled = (method: CustomizationMethod) =>
    (method === 'fine-tuned' && !canFineTune) || (method === 'prompt-tuned' && !canPromptTune);

  const handleContinue = () => {
    onClose();
    const route =
      selectedMethod === 'fine-tuned'
        ? getNewCustomizationJobRoute(workspace, { model: modelRef })
        : getPromptTuningFormRoute(workspace, { model: modelRef });
    navigate(route);
  };

  return (
    <ModalRoot open={open} onOpenChange={onClose}>
      <ModalDialog>
        <ModalContent className="w-2xl">
          <ModalHeading>Customize a Model</ModalHeading>
          <ModalMain className="overflow-y-auto">
            <Stack gap="density-lg" padding="density-lg">
              {canCustomize ? (
                <Text kind="body/regular/md">
                  Select a method to use for customizing your model for your specific use case.
                </Text>
              ) : (
                <Banner kind="inline" status="warning">
                  This model doesn&apos;t support customization. Fine-tuning requires the base
                  weights (a fileset) on the model, and prompt-tuning requires a deployment with
                  LoRA enabled.
                </Banner>
              )}
              <RadioGroupRoot
                name="customization-method"
                value={selectedMethod}
                onValueChange={(value) => setSelectedMethod(value as CustomizationMethod)}
                className="w-full"
              >
                <Stack gap="density-md">
                  {CUSTOMIZATION_METHODS.map((method) => (
                    <RadioCard
                      key={method.value}
                      value={method.value}
                      disabled={isMethodDisabled(method.value)}
                      label={
                        <Flex gap="density-xl" align="center" wrap="wrap">
                          <Text kind="body/bold/lg">{method.title}</Text>
                          <Flex gap="density-sm" align="center" wrap="wrap">
                            {method.tags.map((tag) => (
                              <Tag key={tag} kind="solid" color={method.tagColor}>
                                <span>{tag}</span>
                              </Tag>
                            ))}
                          </Flex>
                        </Flex>
                      }
                      description={
                        <Stack gap="density-md" className="text-left">
                          <Text kind="body/regular/md" color="secondary">
                            {method.description}
                          </Text>
                          <Text kind="body/regular/md" color="secondary">
                            <Text kind="label/bold/md" asChild>
                              <span>Best for:</span>
                            </Text>{' '}
                            {method.bestFor}
                          </Text>
                        </Stack>
                      }
                      labelSide="left"
                    />
                  ))}
                </Stack>
              </RadioGroupRoot>
            </Stack>
          </ModalMain>
          <ModalFooter className="flex w-full justify-end gap-2">
            <Button kind="tertiary" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button color="brand" onClick={handleContinue} type="button" disabled={!canCustomize}>
              Continue
            </Button>
          </ModalFooter>
        </ModalContent>
      </ModalDialog>
    </ModalRoot>
  );
};
