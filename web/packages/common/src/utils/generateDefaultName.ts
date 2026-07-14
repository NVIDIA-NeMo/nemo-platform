// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { adjectives, animals, colors, uniqueNamesGenerator } from 'unique-names-generator';

/**
 * Generates a random default name in the format: adjective-color-animal
 * Examples: "big-purple-mouse", "quick-green-falcon", "calm-blue-dolphin"
 *
 * The generated names are:
 * - Lowercase
 * - Hyphen-separated
 * - Conforming to entity naming validation requirements
 * - Easy to remember but semantically meaningless
 * @param length - The length of the generated name
 */
type Props = {
  length?: number;
  dictionaries?: string[][];
};
export const generateDefaultName = ({
  dictionaries = [adjectives, colors, animals],
  length = 3,
}: Props = {}): string => {
  return uniqueNamesGenerator({
    dictionaries,
    separator: '-',
    length,
    style: 'lowerCase',
  });
};
