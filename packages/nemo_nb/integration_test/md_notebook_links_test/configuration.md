---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

title: "Configuration Reference"
description: "Configuration options for the integration test"
---

<!-- @nemo-nb: process -->

(configuration-reference)=
# Configuration Reference

This page documents the configuration options available for the integration test.

## Basic Configuration

Here's an example of creating a configuration object:

<!-- @nemo-nb: cell python -->
class Config:
	"""Configuration class for the integration test."""
	
	def __init__(self, debug: bool = False):
		self.debug = debug
		self.options = {
			"markdown_format": "notebook",
			"enable_links": True,
			"output_format": "sphinx"
		}
	
	def display(self):
		"""Display current configuration."""
		print("Configuration Settings:")
		print(f"  Debug Mode: {self.debug}")
		print("  Options:")
		for key, value in self.options.items():
			print(f"    - {key}: {value}")

# Create and display configuration
config = Config(debug=True)
config.display()
<!-- @nemo-nb: output stream stdout -->
Configuration Settings:
  Debug Mode: True
  Options:
	- markdown_format: notebook
	- enable_links: True
	- output_format: sphinx
<!-- @nemo-nb: cell markdown -->
## Advanced Options

You can customize the behavior with advanced options:
<!-- @nemo-nb: cell python -->
# Advanced configuration example
advanced_config = {
	"processing": {
		"convert_md_to_nb": True,
		"convert_nb_to_md": True
	},
	"output": {
		"format": "sphinx",
		"extension": ".sphinx.md",
		"build_dir": "_build/nemo-nb"
	},
	"features": [
		"frontmatter",
		"cross-links",
		"output-cells"
	]
}

print("Advanced Configuration:")
for section, settings in advanced_config.items():
	print(f"\n{section.upper()}:")
	if isinstance(settings, dict):
		for key, value in settings.items():
			print(f"  {key}: {value}")
	else:
		print(f"  {settings}")
<!-- @nemo-nb: output stream stdout -->
Advanced Configuration:

PROCESSING:
  convert_md_to_nb: True
  convert_nb_to_md: True

OUTPUT:
  format: sphinx
  extension: .sphinx.md
  build_dir: _build/nemo-nb

FEATURES:
  ['frontmatter', 'cross-links', 'output-cells']

## Related Documentation

- Return to [Getting Started](./getting-started.md) for basic examples
- Visit the [main page](./index.md) for an overview