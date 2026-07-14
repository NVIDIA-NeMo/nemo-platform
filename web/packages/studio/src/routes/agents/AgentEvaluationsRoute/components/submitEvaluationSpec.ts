// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { getSampleAgent } from '@studio/constants/sampleAgents';
import { evalOutputFilesetFor } from '@studio/routes/agents/AgentSuggestionsRoute/utils';

export const MODE_DEFAULT = 'default';
export const MODE_FILESET = 'fileset';

/** Sentinel ``evalConfig`` value that switches the form into create mode. */
export const CREATE_NEW = '__create_new__';

/** Suggested name for a new eval config (e.g. "wise-blue"). */
export const generateEvalConfigName = (): string => generateDefaultName({ length: 2 });

/** Form values the eval-submit modal collects. */
export interface SubmitEvaluationFormValues {
  agent: string;
  /** Existing eval-config fileset to reuse, or CREATE_NEW to make one. */
  evalConfig: string;
  newName: string;
  mode: typeof MODE_DEFAULT | typeof MODE_FILESET;
  exampleKey: string;
  datasetFile: string | null;
}

export interface EvalSeedSource {
  /** Flat filename seeded into the fileset. */
  path: string;
  /** Public asset path fetched on demand for the file's content. */
  assetPath: string;
  type: string;
}

export interface SubmitSpec {
  agent: string;
  evalConfig: string;
  evalConfigFileset: string;
  /** Files to seed into ``evalConfigFileset`` before submitting. Omitted when
   *  reusing an existing config. */
  seedSources?: EvalSeedSource[];
}

export const contentTypeForFile = (name: string): string => {
  if (name.endsWith('.json')) return 'application/json';
  if (name.endsWith('.csv')) return 'text/csv';
  return 'application/yaml';
};

/** Basename of a public asset path — the flat name it's seeded as in the fileset. */
export const fileNameOf = (path: string): string => path.slice(path.lastIndexOf('/') + 1);

/** Builds the eval-job spec from the form (reuse existing config, pick a
 *  fileset YAML, or seed an example into a new fileset). */
export const buildSubmitSpec = (
  formData: SubmitEvaluationFormValues,
  existingConfigs: Map<string, string>
): SubmitSpec => {
  if (formData.evalConfig !== CREATE_NEW) {
    return {
      agent: formData.agent,
      evalConfig: existingConfigs.get(formData.evalConfig) ?? '',
      evalConfigFileset: formData.evalConfig,
    };
  }
  if (formData.mode === MODE_FILESET) {
    // datasetFile is validated by the schema refine before we get here.
    const parsed = parseFilesetLocation(formData.datasetFile!)!;
    return {
      agent: formData.agent,
      evalConfig: parsed.objectPath,
      evalConfigFileset: parsed.name,
    };
  }
  const example = getSampleAgent(formData.exampleKey);
  // Namespace the config per example so switching examples doesn't reuse the
  // first-seeded config.
  const evalConfigName = `${example.key}-${fileNameOf(example.evalConfigPath)}`;
  return {
    agent: formData.agent,
    evalConfig: evalConfigName,
    evalConfigFileset: formData.newName.trim(),
    seedSources: [
      {
        path: evalConfigName,
        assetPath: example.evalConfigPath,
        type: contentTypeForFile(example.evalConfigPath),
      },
      {
        path: fileNameOf(example.evalDataPath),
        assetPath: example.evalDataPath,
        type: contentTypeForFile(example.evalDataPath),
      },
    ],
  };
};

const OUTPUT_SUFFIX_LENGTH = 5;
const OUTPUT_SUFFIX_ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789';

/** Random 5-char suffix so re-runs don't 409 on an existing output fileset. */
const randomSuffix = (): string => {
  const bytes = new Uint8Array(OUTPUT_SUFFIX_LENGTH);
  crypto.getRandomValues(bytes);
  let out = '';
  for (const b of bytes) out += OUTPUT_SUFFIX_ALPHABET[b % OUTPUT_SUFFIX_ALPHABET.length];
  return out;
};

/** Fresh per-run output fileset name (``<agent>-eval-out-<random>``). */
export const generateOutputFilesetName = (agent: string): string =>
  `${evalOutputFilesetFor(agent)}-${randomSuffix()}`;

/** Description stamped on the eval output fileset. */
export const evalOutputDescription = (spec: SubmitSpec): string =>
  `Agent Evaluation output, agent: ${spec.agent}, config: ${spec.evalConfigFileset}`;

/** POST body for ``/jobs/evaluate``. */
export const evaluateRequestBody = (spec: SubmitSpec, output: string) => ({
  spec: {
    agent: spec.agent,
    eval_config: spec.evalConfig,
    eval_config_fileset: spec.evalConfigFileset,
    output,
  },
});
