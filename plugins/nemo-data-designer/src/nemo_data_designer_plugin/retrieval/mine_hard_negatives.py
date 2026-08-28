# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Ported from NVIDIA-NeMo/Nemotron recipes/embed/stage1_data_prep/scripts/mine_hard_negatives.py (Apache-2.0).

from __future__ import annotations

from pathlib import Path

# Automodel ships only in the GPU task image, so these are unresolvable in the
# plugin's CPU environment and in local type checks.
from nemo_automodel._transformers.auto_model import NeMoAutoModelBiEncoder  # ty: ignore[unresolved-import]
from nemo_automodel.components.config._arg_parser import parse_args_and_load_config  # ty: ignore[unresolved-import]
from nemo_automodel.recipes.retrieval import mine_hard_negatives as automodel_mining  # ty: ignore[unresolved-import]


class MineHardNegativesRecipe(automodel_mining.MineHardNegativesRecipe):
    """Automodel miner that explicitly supports trusted custom HF architectures."""

    def setup(self):
        self.dist_env = automodel_mining.build_distributed(self.cfg.get("dist_env", {}))
        self.mining_cfg = self.cfg.get("mining", None)
        if self.mining_cfg is None:
            raise ValueError("Missing mining configuration")

        self._extract_mining_params()
        self._validate_mining_params()

        model_kwargs = {
            "use_liger_kernel": False,
            "use_sdpa_patching": True,
            "trust_remote_code": self._get_mining_param("trust_remote_code", False),
        }
        if self.attn_implementation is not None:
            model_kwargs["attn_implementation"] = self.attn_implementation

        automodel_mining.logger.info(f"Loading encoder model from {self.model_name_or_path}...")
        self.model = NeMoAutoModelBiEncoder.from_pretrained(self.model_name_or_path, **model_kwargs)
        self.model = self.model.to(self.dist_env.device)
        self.model.eval()
        self._configure_tokenizer()
        self._load_data()
        self._build_document_mappings()
        self._prepare_data()


def main(default_config_path: str | None = None) -> None:
    if default_config_path is None:
        default_config_path = str(Path(__file__).with_name("mining_config.yaml"))
    cfg = parse_args_and_load_config(default_config_path)
    recipe = MineHardNegativesRecipe(cfg)
    recipe.setup()
    recipe.run()


if __name__ == "__main__":
    main()
