// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EntityNameField } from '@nemo/common/src/components/EntityNameField';
import type { Meta, StoryObj } from '@storybook/react';
import { useState } from 'react';

// Simulated backend: these names are "taken" by another entity, to exercise
// the uniqueness-conflict state without a real API.
const TAKEN_NAMES = ['my-fileset', 'production-secret'];

const fakeCheckAvailability = (name: string): Promise<boolean> => {
  const { promise, resolve } = Promise.withResolvers<boolean>();
  setTimeout(() => resolve(TAKEN_NAMES.includes(name)), 600);
  return promise;
};

const meta: Meta<typeof EntityNameField> = {
  title: 'Common/EntityNameField',
  component: EntityNameField,
  decorators: [
    (Story) => (
      <div className="w-[420px]">
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof EntityNameField>;

/**
 * No uniqueness constraint. Type "Foo bar" or "MyProject" and watch the
 * description below the field update live, while the input itself keeps
 * exactly what you typed. Blur the field afterward — since the sanitized
 * name is what actually gets submitted, cosmetic differences like these
 * never turn into a form error.
 */
export const Default: Story = {
  render: function DefaultStory() {
    const [value, setValue] = useState('');
    return <EntityNameField entity="fileset" value={value} onChange={setValue} />;
  },
};

/**
 * Blur with input that sanitizes to nothing usable (e.g. only symbols) to
 * see the one case that *does* error after blur — there's no valid name to
 * submit.
 */
export const NothingValidToSubmit: Story = {
  render: function NothingValidToSubmitStory() {
    const [value, setValue] = useState('!!!');
    return <EntityNameField entity="fileset" value={value} onChange={setValue} />;
  },
};

/**
 * Uniqueness enforced via `checkAvailability`. Type "my-fileset" or
 * "production-secret" to see "Checking name..." while the debounced query
 * is in flight, then the "already exists" error — surfaced immediately,
 * without needing to blur.
 */
export const WithUniquenessCheck: Story = {
  render: function WithUniquenessCheckStory() {
    const [value, setValue] = useState('');
    return (
      <EntityNameField
        entity="fileset"
        value={value}
        onChange={setValue}
        checkAvailability={fakeCheckAvailability}
      />
    );
  },
};

/** Pre-filled with a name that already conflicts, to inspect the error state directly. */
export const NameAlreadyExists: Story = {
  render: function NameAlreadyExistsStory() {
    const [value, setValue] = useState('my-fileset');
    return (
      <EntityNameField
        entity="fileset"
        value={value}
        onChange={setValue}
        checkAvailability={fakeCheckAvailability}
      />
    );
  },
};

/** Disabled field, e.g. renaming an entity that doesn't support it. */
export const Disabled: Story = {
  args: { entity: 'dataset', value: 'my-dataset', onChange: () => {}, disabled: true },
};
