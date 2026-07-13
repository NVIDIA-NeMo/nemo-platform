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

/**
 * Suggests a short, memorable, semantically-meaningless name for a reusable
 * eval config (e.g. "wise-pretzel"). Two words (adjective-animal) keep it
 * readable in a dropdown while staying valid as a fileset name.
 */
export const generateEvalConfigName = (): string =>
  generateDefaultName({ dictionaries: [adjectives, animals], length: 2 });
