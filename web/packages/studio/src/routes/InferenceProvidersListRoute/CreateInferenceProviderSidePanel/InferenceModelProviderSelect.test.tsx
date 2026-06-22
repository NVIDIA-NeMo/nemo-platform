/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { FormField } from '@nvidia/foundations-react-core';
import { InferenceModelProviderSelect } from '@studio/routes/InferenceProvidersListRoute/CreateInferenceProviderSidePanel/InferenceModelProviderSelect';
import { render } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('InferenceModelProviderSelect a11y wiring', () => {
  it('SelectTrigger gets accessible name/description from enclosing FormField via context', async () => {
    render(
      <FormField
        name="model-provider"
        slotLabel="Model Provider"
        slotError="Please pick a provider"
        status="error"
      >
        <InferenceModelProviderSelect
          value="custom"
          onValueChange={() => {}}
          isPresetDisabled={() => false}
        />
      </FormField>
    );

    const trigger = await screen.findByRole('combobox', { name: /model provider/i });

    expect(trigger).toHaveAccessibleName(/model provider/i);
    expect(trigger).toHaveAccessibleDescription(/please pick a provider/i);
  });
});
