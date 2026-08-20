// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  AgentConfigParseError,
  agentNameFromConfig,
  agentSpecFilesetName,
  collectAgentEntries,
  isIgnoredPath,
  MAX_AGENT_SPEC_FILES,
  parseAgentConfig,
  validateAgentEntries,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/const';
import type { UploadAgentEntry } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';

const makeFile = (relativePath: string, contents = 'x'): File => {
  const file = new File([contents], relativePath.split('/').pop() ?? relativePath);
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
};

const entry = (path: string, size = 1): UploadAgentEntry => ({
  path,
  file: { size } as File,
});

describe('collectAgentEntries', () => {
  it('strips the picked directory from each path', () => {
    const entries = collectAgentEntries([
      makeFile('calculator-agent/agent.yaml'),
      makeFile('calculator-agent/mcps/calculator.py'),
    ]);

    expect(entries.map((item) => item.path)).toEqual(['agent.yaml', 'mcps/calculator.py']);
  });

  it('drops build artifacts that the container path cannot stage', () => {
    const entries = collectAgentEntries([
      makeFile('agent/agent.yaml'),
      makeFile('agent/mcps/__pycache__/calculator.cpython-312.pyc'),
      makeFile('agent/.DS_Store'),
      makeFile('agent/.git/config'),
      makeFile('agent/node_modules/left-pad/index.js'),
    ]);

    expect(entries.map((item) => item.path)).toEqual(['agent.yaml']);
  });

  it('falls back to the file name when the picker reports no relative path', () => {
    const entries = collectAgentEntries([new File(['x'], 'agent.yaml')]);

    expect(entries.map((item) => item.path)).toEqual(['agent.yaml']);
  });
});

describe('isIgnoredPath', () => {
  it.each([
    ['mcps/__pycache__/calculator.pyc', true],
    ['.venv/lib/python3.12/site-packages/x.py', true],
    ['build/libthing.so', true],
    ['skills/review/SKILL.md', false],
    ['mcps/calculator.py', false],
  ])('%s -> %s', (path, expected) => {
    expect(isIgnoredPath(path)).toBe(expected);
  });
});

describe('validateAgentEntries', () => {
  it('requires agent.yaml at the top level', () => {
    expect(validateAgentEntries([entry('mcps/calculator.py')])).toMatch(/No agent\.yaml/);
    expect(validateAgentEntries([entry('nested/agent.yaml')])).toMatch(/No agent\.yaml/);
  });

  it('rejects an empty directory', () => {
    expect(validateAgentEntries([])).toMatch(/no uploadable files/);
  });

  it('rejects a directory over the file-count limit', () => {
    const entries = [
      entry('agent.yaml'),
      ...Array.from({ length: MAX_AGENT_SPEC_FILES }, (_unused, index) => entry(`f${index}.md`)),
    ];

    expect(validateAgentEntries(entries)).toMatch(/the limit is 500/);
  });

  it('rejects a directory over the byte limit', () => {
    expect(validateAgentEntries([entry('agent.yaml', 900_001)])).toMatch(/the limit is 900 KB/);
  });

  it('accepts a directory within both limits', () => {
    expect(validateAgentEntries([entry('agent.yaml'), entry('mcps/calculator.py')])).toBeUndefined();
  });
});

describe('parseAgentConfig', () => {
  it('returns the parsed config for the Fabric contract', () => {
    const config = parseAgentConfig('config_format: nemo-agents-spec-v1\nname: calc\n');

    expect(config.name).toBe('calc');
  });

  it('rejects a NAT workflow config', () => {
    expect(() => parseAgentConfig('config_format: nat-workflow-v1\n')).toThrow(
      AgentConfigParseError
    );
  });

  it('rejects a config with no config_format', () => {
    expect(() => parseAgentConfig('name: calc\n')).toThrow(AgentConfigParseError);
  });

  it('rejects YAML that is not a mapping', () => {
    expect(() => parseAgentConfig('- one\n- two\n')).toThrow(/must contain a YAML mapping/);
  });

  it('rejects malformed YAML', () => {
    expect(() => parseAgentConfig('a:\n  - b\n c: broken\n')).toThrow(/not valid YAML/);
  });
});

describe('agentNameFromConfig', () => {
  it('reads a non-empty name', () => {
    expect(agentNameFromConfig({ name: ' calc ' })).toBe('calc');
  });

  it('ignores a missing or blank name', () => {
    expect(agentNameFromConfig({})).toBeUndefined();
    expect(agentNameFromConfig({ name: '   ' })).toBeUndefined();
    expect(agentNameFromConfig({ name: 7 })).toBeUndefined();
  });
});

describe('agentSpecFilesetName', () => {
  it('matches the platform convention', () => {
    expect(agentSpecFilesetName('calc')).toBe('calc-spec');
  });
});
