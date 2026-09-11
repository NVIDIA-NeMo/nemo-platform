<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Candidate record shape

Read this when writing the Step 5 decision. Replace illustrative values with
reviewed evidence; this example is not a ready candidate while required software
availability remains unknown. The helper validates the record during finalization.

```json
{
  "schema": "nemo.eval_author.trace_environment_candidate.v2",
  "status": "candidate",
  "decision_basis": "safe_atif_only",
  "instruction": "Observable task instruction without private values",
  "requirements": [
    {"description": "Objectively testable requirement", "evidence_steps": [1, 2]}
  ],
  "verification_mode": "execution",
  "evidence_steps": [1, 2],
  "uncertainties": [],
  "reason_codes": [],
  "ground_truth": {
    "availability": "available",
    "use": "comparison_only",
    "artifacts": [
      {
        "kind": "expected_output",
        "path": "private/ground-truth/expected.json",
        "sha256": "sha256:<64-hex-digest>",
        "provenance": {
          "kind": "external",
          "step_ids": [],
          "uri": "https://example.test/fixture.json",
          "revision": "<immutable-revision>",
          "source_id": null
        },
        "notes": "Expected output attached to the recorded task."
      }
    ],
    "absence_reason": null
  },
  "software_requirements": [
    {
      "name": "ExampleCAD",
      "category": "desktop_application",
      "required": true,
      "version": "2026",
      "license": "proprietary",
      "availability": "unknown",
      "redistributable": false,
      "provenance": {
        "kind": "atif_step",
        "step_ids": [1, 2],
        "uri": null,
        "revision": null,
        "source_id": null
      },
      "notes": "The requested edit and verifier depend on native CAD behavior."
    }
  ]
}
```
