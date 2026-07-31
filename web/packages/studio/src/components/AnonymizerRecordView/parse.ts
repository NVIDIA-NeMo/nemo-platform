// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  AnonymizerEntity,
  AnonymizerRecord,
  EntityReplacement,
  TextSegment,
} from '@studio/components/AnonymizerRecordView/types';
import { asRecord } from '@studio/util/guards';

const DETECTED_ENTITIES_COLUMN = '_detected_entities';
const FINAL_ENTITIES_COLUMN = 'final_entities';
const REPLACEMENT_MAP_COLUMN = '_replacement_map';

/** Rewrite writes `<column>_rewritten`; the replace strategies write `<column>_replaced`. */
export const REWRITTEN_SUFFIX = '_rewritten';
export const REPLACED_SUFFIX = '_replaced';
export const OUTPUT_SUFFIXES = [REWRITTEN_SUFFIX, REPLACED_SUFFIX] as const;

/** Trace cells arrive either already decoded or as a JSON string, depending on the writer. */
const decodeCell = (value: unknown): unknown => {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return undefined;
  }
};

const wrappedList = (cell: unknown, key: string): unknown[] => {
  const entries = asRecord(decodeCell(cell))?.[key];
  return Array.isArray(entries) ? entries : [];
};

const toEntity = (entry: unknown): AnonymizerEntity | undefined => {
  const row = asRecord(entry);
  if (!row) return undefined;
  const { value, label, start_position: start, end_position: end } = row;
  if (typeof label !== 'string' || typeof start !== 'number' || typeof end !== 'number') {
    return undefined;
  }
  return { value: typeof value === 'string' ? value : '', label, start, end };
};

export const parseEntities = (cell: unknown): AnonymizerEntity[] =>
  wrappedList(cell, 'entities').flatMap((entry) => {
    const entity = toEntity(entry);
    return entity ? [entity] : [];
  });

export const parseReplacements = (cell: unknown): EntityReplacement[] =>
  wrappedList(cell, 'replacements').flatMap((entry) => {
    const row = asRecord(entry);
    const { original, label, synthetic } = row ?? {};
    return typeof original === 'string' &&
      typeof label === 'string' &&
      typeof synthetic === 'string'
      ? [{ original, label, synthetic }]
      : [];
  });

const byPosition = (a: AnonymizerEntity, b: AnonymizerEntity): number =>
  a.start - b.start || a.end - b.end;

export const toSegments = (text: string, entities: readonly AnonymizerEntity[]): TextSegment[] => {
  if (!entities.length) return text ? [{ text }] : [];

  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const entity of [...entities].sort(byPosition)) {
    if (entity.start < cursor || entity.end <= entity.start || entity.end > text.length) continue;
    if (entity.start > cursor) segments.push({ text: text.slice(cursor, entity.start) });
    segments.push({ text: text.slice(entity.start, entity.end), label: entity.label });
    cursor = entity.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments;
};

interface SyntheticLookups {
  readonly byValueLabel: Map<string, string>;
  readonly byValue: Map<string, string>;
  readonly byValueLabelLower: Map<string, string>;
  readonly byValueLower: Map<string, string>;
}

// Label first so the newline separator stays unambiguous — labels never contain one, values may.
const lookupKey = (value: string, label: string): string => `${label}\n${value}`;

const buildSyntheticLookups = (replacements: readonly EntityReplacement[]): SyntheticLookups => {
  const lookups: SyntheticLookups = {
    byValueLabel: new Map(),
    byValue: new Map(),
    byValueLabelLower: new Map(),
    byValueLower: new Map(),
  };
  for (const { original, label, synthetic } of replacements) {
    const lower = original.toLowerCase();
    lookups.byValueLabel.set(lookupKey(original, label), synthetic);
    lookups.byValue.set(original, synthetic);
    lookups.byValueLabelLower.set(lookupKey(lower, label), synthetic);
    lookups.byValueLower.set(lower, synthetic);
  }
  return lookups;
};

/** Exact value+label, then value only, then both again case-insensitively. */
const resolveSynthetic = (entity: AnonymizerEntity, lookups: SyntheticLookups): string => {
  const lower = entity.value.toLowerCase();
  return (
    lookups.byValueLabel.get(lookupKey(entity.value, entity.label)) ??
    lookups.byValue.get(entity.value) ??
    lookups.byValueLabelLower.get(lookupKey(lower, entity.label)) ??
    lookups.byValueLower.get(lower) ??
    entity.value
  );
};

/** Searches forward for each synthetic value; replaying offsets drifts when lengths change. */
export const buildReplacedEntities = (
  originalEntities: readonly AnonymizerEntity[],
  replacements: readonly EntityReplacement[],
  originalText: string,
  replacedText: string
): AnonymizerEntity[] => {
  const lookups = buildSyntheticLookups(replacements);
  const replaced: AnonymizerEntity[] = [];
  let originalCursor = 0;
  let searchFrom = 0;

  for (const entity of [...originalEntities].sort(byPosition)) {
    const { start, end, label } = entity;
    if (start < originalCursor || end <= start || end > originalText.length) continue;

    const originalSpan = originalText.slice(start, end);
    let synthetic = resolveSynthetic(entity, lookups);
    let position = synthetic ? replacedText.indexOf(synthetic, searchFrom) : -1;
    if (position < 0 && synthetic !== originalSpan) {
      position = replacedText.indexOf(originalSpan, searchFrom);
      if (position >= 0) synthetic = originalSpan;
    }

    originalCursor = end;
    if (position < 0) continue;

    replaced.push({
      value: replacedText.slice(position, position + synthetic.length),
      label,
      start: position,
      end: position + synthetic.length,
    });
    searchFrom = position + synthetic.length;
  }

  return replaced;
};

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Fallback for when detection produced no spans but the replacement map did. */
const entitiesByCaseInsensitiveSearch = (
  replacements: readonly EntityReplacement[],
  text: string
): AnonymizerEntity[] =>
  replacements
    .flatMap(({ original, label }) => {
      if (!original || !label) return [];
      return [...text.matchAll(new RegExp(escapeRegExp(original), 'gi'))].map((match) => ({
        value: match[0],
        label,
        start: match.index,
        end: match.index + match[0].length,
      }));
    })
    .sort(byPosition);

const entitiesBySyntheticSearch = (
  replacements: readonly EntityReplacement[],
  text: string
): AnonymizerEntity[] =>
  replacements
    .flatMap(({ synthetic, label }) => {
      if (!synthetic || !label) return [];
      return [...text.matchAll(new RegExp(escapeRegExp(synthetic), 'g'))].map((match) => ({
        value: synthetic,
        label,
        start: match.index,
        end: match.index + synthetic.length,
      }));
    })
    .sort(byPosition);

const asText = (value: unknown): string => (typeof value === 'string' ? value : '');

export const outputColumn = (
  row: Record<string, unknown>,
  textColumn: string
): string | undefined =>
  OUTPUT_SUFFIXES.map((suffix) => `${textColumn}${suffix}`).find((column) => column in row);

export const buildAnonymizerRecord = (
  row: Record<string, unknown>,
  textColumn: string
): AnonymizerRecord => {
  const original = asText(row[textColumn]);
  const outputKey = outputColumn(row, textColumn);
  const replaced = outputKey ? asText(row[outputKey]) : '';
  const replacements = parseReplacements(row[REPLACEMENT_MAP_COLUMN]);

  const detected =
    FINAL_ENTITIES_COLUMN in row
      ? parseEntities(row[FINAL_ENTITIES_COLUMN])
      : parseEntities(row[DETECTED_ENTITIES_COLUMN]);
  const originalEntities = detected.length
    ? detected
    : entitiesByCaseInsensitiveSearch(replacements, original);

  const derived = buildReplacedEntities(originalEntities, replacements, original, replaced);
  const replacedEntities = derived.length
    ? derived
    : entitiesBySyntheticSearch(replacements, replaced);

  return {
    original,
    replaced,
    originalSegments: toSegments(original, originalEntities),
    replacedSegments: toSegments(replaced, replacedEntities),
    replacements,
  };
};
