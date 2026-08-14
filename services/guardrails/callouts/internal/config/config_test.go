// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package config

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestLoadYaml(t *testing.T) {
	tmp := t.TempDir() // auto-cleaned up after the test

	// Helper to write a file
	write := func(name string, data []byte) string {
		p := filepath.Join(tmp, name)
		if err := os.WriteFile(p, data, 0o644); err != nil {
			t.Fatalf("write %s: %v", name, err)
		}
		return p
	}

	// Prepare a YAML file with partial overrides
	yamlPath := write("cfg.yaml", []byte(`
guardrails:
  models:
    fake_model:
      config_ids:
        - nemoguard
        - jailbreak
    fake_model2:
      refusal_text: "对不起，我不能回答"
      config_ids:
        - nemoguard
`))

	want := defaults()
	want.Guardrails.Models = map[string]GuardrailsModelConfig{
		"fake_model": {
			RefusalText: "",
			ConfigIDs:   []string{"nemoguard", "jailbreak"},
		},
		"fake_model2": {
			RefusalText: "对不起，我不能回答",
			ConfigIDs:   []string{"nemoguard"},
		},
	}

	got, err := Load(yamlPath)
	if err != nil {
		t.Fatalf("Load(yamlPath) errored unexpectedly: %v", err)
	}

	if diff := cmp.Diff(want, got); diff != "" {
		t.Fatalf("Config mismatch (-want +got)\n%s", diff)
	}
}
