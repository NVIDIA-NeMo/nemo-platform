// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { storageConfigFromUrl } from '@studio/util/storageConfigFromUrl';

describe('storageConfigFromUrl', () => {
  describe('Hugging Face', () => {
    it('parses dataset URL and returns HuggingfaceStorageConfig', () => {
      const config = storageConfigFromUrl({
        url: 'https://huggingface.co/datasets/databricks/databricks-dolly-15k',
      });

      expect(config.type).toBe('huggingface');
      expect(config).toMatchObject({
        type: 'huggingface',
        repo_id: 'databricks/databricks-dolly-15k',
        repo_type: 'dataset',
        endpoint: 'https://huggingface.co',
      });
      expect(config).not.toHaveProperty('token_secret');
    });

    it('parses model URL and sets repo_type model', () => {
      const config = storageConfigFromUrl({
        url: 'https://huggingface.co/meta-llama/Llama-2-7b',
      });

      expect(config).toMatchObject({
        type: 'huggingface',
        repo_id: 'meta-llama/Llama-2-7b',
        repo_type: 'model',
        endpoint: 'https://huggingface.co',
      });
    });

    it('parses space URL and sets repo_type space', () => {
      const config = storageConfigFromUrl({
        url: 'https://huggingface.co/spaces/username/my-space',
      });

      expect(config).toMatchObject({
        type: 'huggingface',
        repo_id: 'username/my-space',
        repo_type: 'space',
      });
    });

    it('includes token_secret when secretKey is provided', () => {
      const config = storageConfigFromUrl({
        url: 'https://huggingface.co/datasets/org/repo',
        secretKey: 'my-hf-token',
      });

      expect(config).toMatchObject({
        type: 'huggingface',
        repo_id: 'org/repo',
        token_secret: 'my-hf-token',
      });
    });

    it('uses custom endpoint when URL has non-default host', () => {
      expect(() =>
        storageConfigFromUrl({
          url: 'https://hub.example.com/datasets/org/repo',
        })
      ).toThrow(/Unsupported storage URL/);
    });

    it('throws on invalid Hugging Face path', () => {
      expect(() => storageConfigFromUrl({ url: 'https://huggingface.co/single-segment' })).toThrow(
        /Invalid Hugging Face URL/
      );
    });
  });

  describe('NGC', () => {
    it('parses catalog URL and returns NGCStorageConfig', () => {
      const config = storageConfigFromUrl({
        url: 'https://catalog.ngc.nvidia.com/orgs/nvidia/teams/ngc-apps/resources/ngc_cli',
        secretKey: 'ngc-api-key',
      });

      expect(config.type).toBe('ngc');
      expect(config).toMatchObject({
        type: 'ngc',
        org: 'nvidia',
        team: 'ngc-apps',
        target: 'ngc_cli',
        api_key_secret: 'ngc-api-key',
        host: 'https://api.ngc.nvidia.com',
      });
    });

    it('parses api.ngc.nvidia.com host', () => {
      const config = storageConfigFromUrl({
        url: 'https://api.ngc.nvidia.com/orgs/my-org/teams/my-team/resources/my-resource',
        secretKey: 'secret',
      });

      expect(config).toMatchObject({
        type: 'ngc',
        org: 'my-org',
        team: 'my-team',
        target: 'my-resource',
        api_key_secret: 'secret',
      });
    });

    it('throws when secretKey is missing for NGC URL', () => {
      expect(() =>
        storageConfigFromUrl({
          url: 'https://catalog.ngc.nvidia.com/orgs/nvidia/teams/ngc-apps/resources/ngc_cli',
        })
      ).toThrow('secretKey is required for NGC storage config');
    });

    it('throws on invalid NGC path', () => {
      expect(() =>
        storageConfigFromUrl({
          url: 'https://catalog.ngc.nvidia.com/orgs/nvidia',
          secretKey: 'key',
        })
      ).toThrow(/Invalid NGC URL/);
    });
  });

  describe('errors', () => {
    it('throws on invalid URL string', () => {
      expect(() => storageConfigFromUrl({ url: 'not-a-url' })).toThrow(/Invalid storage URL/);
    });

    it('throws on unsupported host', () => {
      expect(() =>
        storageConfigFromUrl({ url: 'https://example.com/orgs/a/teams/b/resources/c' })
      ).toThrow(/Unsupported storage URL/);
    });
  });
});
