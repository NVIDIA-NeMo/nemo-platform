# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Expected to run as a sidecar to the NIM container with the same ENV Vars"""

import asyncio
import json
import logging
import os
import shutil
import signal
import threading

from nemo_platform import NeMoPlatform, NotFoundError
from nemo_platform.types.models import ModelEntity
from nemo_platform.types.models.adapter import Adapter
from nmp.common.config import get_platform_config
from nmp.common.controller import Controller, ControllerManager, Loop, TimedLoopWaiter, TrackLastExecutionTime
from nmp.common.sdk_factory import get_platform_sdk

stop_signal = threading.Event()

# Global reference to monitor control loop health
adapters_controller_monitored = None

logger = logging.getLogger(__name__)

ADAPTER_META_FILENAME = "nmp_adapter_meta.json"


class AdaptersController(Controller):
    def __init__(self, stop_signal: threading.Event | None = None):
        self.nim_peft_source = os.getenv("NIM_PEFT_SOURCE", "")
        if not self.nim_peft_source:
            msg = "NIM_PEFT_SOURCE is not set on the container"
            logger.warning(msg)
            raise ValueError(msg)

        os.makedirs(self.nim_peft_source, exist_ok=True)

        if not os.path.isdir(self.nim_peft_source):
            msg = "NIM_PEFT_SOURCE is not a directory"
            logger.error(msg)
            raise ValueError(msg)

        self.workspace = os.getenv("NMP_MODEL_ENTITY_WORKSPACE", "")
        self.model_name = os.getenv("NMP_MODEL_ENTITY_NAME", "")

        if not self.workspace:
            msg = "NMP_MODEL_ENTITY_WORKSPACE must be set to download loras"
            logger.error(msg)
            raise ValueError(msg)

        if not self.model_name:
            msg = "NMP_MODEL_ENTITY_NAME must be set to download loras"
            logger.error(msg)
            raise ValueError(msg)

        # vLLM's lora_filesystem_resolver only auto-loads an adapter whose
        # adapter_config.json ``base_model_name_or_path`` equals vLLM's ``--model``
        # value (the local model path). Adapters arrive from the Files service with
        # their original base-model name, so when this override is set (vLLM only)
        # we rewrite each downloaded adapter's base name to match. Empty for NIM,
        # which scans the directory and does not require this equality.
        self.base_model_name_override = os.getenv("VLLM_LORA_BASE_MODEL_OVERRIDE", "")

        self._stop_signal = stop_signal

        self._loop = asyncio.new_event_loop()

        self.platform_config = get_platform_config()

        self._sdk: NeMoPlatform = get_platform_sdk(
            as_service="models",
            internal=True,
        )

    def download_fileset(self, dest_dir: str, workspace: str, name: str) -> bool:
        try:
            response = self._sdk.files.list(
                workspace=workspace,
                fileset=name,
            )
            logger.info(f"Found {len(response.data)} files in FileSet {workspace}/{name}")
            if not response.data:
                logger.warning(f"FileSet {workspace}/{name} contains no files")
                return False

            # TODO: Add reporting on download progress and store it with the Adapter on ModelEntity

            self._sdk.files.download(
                fileset=name,
                workspace=workspace,
                local_path=dest_dir,
            )
            return True

        except NotFoundError:
            return False

    def step(self):
        """Override to perform updates."""

        try:
            dirs_to_keep: set[str] = set()
            self._update_lora_adapters(dirs_to_keep)
            self._update_prompt_tuned_models(dirs_to_keep)

            for name in set(os.listdir(self.nim_peft_source)) - dirs_to_keep:
                shutil.rmtree(f"{self.nim_peft_source}/{name}")

        except Exception:
            logger.exception(f"Failed to fetch {self.workspace}/{self.model_name}'s model_entity")
            return

    def _update_prompt_tuned_models(self, dirs_to_keep: set[str]):
        # Prompt-tuned variants are intentionally NOT migrated to the
        # ``{adapter_ws}--{adapter_name}`` encoding used by LoRA adapters
        # (AALGO-129): they remain single-workspace for now and continue to
        # use the bare model_entity.name as their on-disk directory.
        logger.info(f"Fetching prompt data for {self.workspace}/{self.model_name}")
        model_entities: list[ModelEntity] = self._sdk.models.list(
            workspace=self.workspace,
            filter={
                "base_model": self.model_name,
            },
        )
        for model_entity in model_entities:
            if model_entity.prompt:
                dirs_to_keep.add(model_entity.name)
                prompt_tuned_model_dir = f"{self.nim_peft_source}/{model_entity.name}"
                if not os.path.isdir(prompt_tuned_model_dir):
                    os.makedirs(prompt_tuned_model_dir, exist_ok=True)
                with open(f"{prompt_tuned_model_dir}/config.json", "w") as f:
                    f.write(model_entity.prompt.model_dump_json())

    def _rewrite_adapter_base_model(self, adapter_dir: str) -> bool:
        """Rewrite ``adapter_config.json``'s ``base_model_name_or_path`` to the
        configured override so vLLM's filesystem resolver will match and auto-load
        the adapter against the locally served base model.

        Returns ``True`` on success, ``False`` if the config is missing or can't be
        read/written. The caller must not publish the adapter on ``False``: a
        non-rewritten adapter would never auto-resolve in vLLM, and refusing to
        publish keeps it eligible for retry on the next cycle.
        """
        cfg_path = os.path.join(adapter_dir, "adapter_config.json")
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read adapter_config.json in {adapter_dir} to rewrite base model: {e}")
            return False
        cfg["base_model_name_or_path"] = self.base_model_name_override
        try:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f)
        except OSError as e:
            logger.warning(f"Could not write rewritten adapter_config.json in {adapter_dir}: {e}")
            return False
        return True

    def _write_adapter_meta(self, adapter_dir: str, adapter: Adapter) -> None:
        """Persist adapter metadata so future cycles can detect fileset changes."""
        meta_path = os.path.join(adapter_dir, ADAPTER_META_FILENAME)
        meta = {
            "fileset": adapter.fileset,
            "updated_at": adapter.updated_at.isoformat() if adapter.updated_at else None,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f)

    def _adapter_changed(self, adapter_dir: str, adapter: Adapter) -> bool:
        """Return True if the on-disk adapter is stale compared to the API state."""
        meta_path = os.path.join(adapter_dir, ADAPTER_META_FILENAME)
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Missing or corrupt metadata -- treat as changed to be safe
            logger.info(
                f"Cannot open adapter metadata file for {adapter.name}, files might be corrupted, re-downloading"
            )
            return True

        if meta.get("fileset") != adapter.fileset:
            logger.info(f"Adapter {adapter.name} fileset changed, re-downloading")
            return True

        stored_updated_at = meta.get("updated_at")
        current_updated_at = adapter.updated_at.isoformat() if adapter.updated_at else None
        if stored_updated_at != current_updated_at:
            logger.info(f"Adapter {adapter.name} updated_at changed, re-downloading")
            return True

        return False

    def _download_adapter(self, adapter_dir: str, adapter: Adapter, adapter_workspace: str) -> None:
        """Download adapter fileset atomically using a temp directory + rename.

        Downloads into a sibling temp directory inside nim_peft_source, then
        swaps it into place with os.rename (atomic on the same filesystem).
        This prevents NIM from seeing a partially-downloaded or empty adapter
        directory during the swap. We use the same logic in files service in
        nmp/services/core/files/src/nmp/core/files/app/backends/local.py

        The staging directory is named ``.{basename(adapter_dir)}.tmp`` rather
        than ``.{adapter.name}.tmp`` so concurrent refreshes of same-named
        adapters in different workspaces (whose ``adapter_dir`` paths are
        ``{adapter_ws}--{adapter.name}``) cannot collide on a shared temp path.

        ``adapter_workspace`` is the workspace the *adapter* lives in (resolved
        upstream by :meth:`_resolve_adapter_workspace`). Bare ``adapter.fileset``
        values (no ``"{ws}/"`` prefix) are anchored here, not on the base model's
        workspace: the fileset was uploaded by whoever created the adapter, which
        means it lives in the adapter's workspace. Using the base model's workspace
        instead would silently mis-route fileset fetches whenever the adapter and
        base model live in different workspaces.
        """
        parts = adapter.fileset.split("/", 1)
        if len(parts) == 1:
            fileset_workspace = adapter_workspace
            fileset_name = parts[0]
        else:
            fileset_workspace = parts[0]
            fileset_name = parts[1]

        temp_dir = os.path.join(self.nim_peft_source, f".{os.path.basename(adapter_dir)}.tmp")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            if self.download_fileset(temp_dir, fileset_workspace, fileset_name):
                if self.base_model_name_override and not self._rewrite_adapter_base_model(temp_dir):
                    # Don't publish an adapter we couldn't rewrite for vLLM: it would
                    # never auto-resolve. Raising here cleans up the temp dir (below)
                    # and leaves the adapter un-published so it retries next cycle.
                    raise RuntimeError(
                        f"Failed to rewrite adapter_config.json base model for {adapter.name}; "
                        "refusing to publish adapter directory"
                    )
                self._write_adapter_meta(temp_dir, adapter)
                # os.rename fails if the destination directory already exists,
                # so remove the old adapter dir first when updating in-place.
                if os.path.isdir(adapter_dir):
                    shutil.rmtree(adapter_dir)
                os.rename(temp_dir, adapter_dir)
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    @staticmethod
    def _resolve_adapter_workspace(adapter: Adapter, base_model_workspace: str) -> str:
        """Return the workspace where ``adapter`` lives.

        The flat ``{adapter_ws}--{adapter_name}`` directory layout needs each
        adapter's own workspace to disambiguate cross-workspace name
        collisions. The internal :class:`Adapter` entity carries ``workspace``,
        but the public API/SDK schema does not yet expose it. Until it does,
        fall back to the base model's workspace: the on-disk encoding stays in
        the ``{ws}--{name}`` form so every directory the reconciler sees is
        decodable — just collapsed onto the base model's workspace, matching
        the legacy single-workspace assumption.

        TODO: drop the ``getattr`` fallback once ``Adapter`` exposes
        ``workspace`` in the SDK schema; the read becomes ``adapter.workspace``.
        """
        return getattr(adapter, "workspace", None) or base_model_workspace

    def _update_lora_adapters(self, dirs_to_keep: set[str]):
        """Materialize each enabled LoRA adapter into ``{nim_peft_source}/{adapter_ws}--{adapter_name}/``.

        The flat ``{adapter_ws}--{adapter_name}`` encoding lets cross-workspace
        adapters with colliding names coexist on disk while remaining visible
        to NIM's flat scanner (``nvext_peft.LoRAModelSynchronizer.synchronize_local_dir``
        does a single non-recursive ``os.listdir`` of ``NIM_PEFT_SOURCE``, so a
        nested ``{ws}/{name}/`` layout would silently drop every adapter).
        ``--`` is safe because the entity-store ``NAME_PATTERN`` forbids two
        consecutive hyphens in any workspace or entity name, so the reconciler
        can losslessly recover ``(adapter_ws, adapter_name)`` via
        ``mid.partition("--")``.
        """
        logger.info(f"Fetching adapters for {self.workspace}/{self.model_name}")

        model_entity: ModelEntity = self._sdk.models.retrieve(name=self.model_name, workspace=self.workspace)
        if not model_entity.adapters:
            return

        for adapter in model_entity.adapters:
            if not adapter.enabled:
                continue
            if not adapter.fileset:
                logger.warning(f"Adapter {adapter.name} has no fileset, skipping")
                continue

            adapter_workspace = self._resolve_adapter_workspace(adapter, model_entity.workspace)
            dir_name = f"{adapter_workspace}--{adapter.name}"
            dirs_to_keep.add(dir_name)
            adapter_dir = f"{self.nim_peft_source}/{dir_name}"
            if not os.path.isdir(adapter_dir) or self._adapter_changed(adapter_dir, adapter):
                self._download_adapter(adapter_dir, adapter, adapter_workspace)


def get_health_status() -> dict:
    """Get the health status of the adapters controller."""
    if adapters_controller_monitored:
        if adapters_controller_monitored.is_healthy:
            return {"status": "ready"}
    return {"status": "not ready"}


def handle_sighup(signum, frame):
    """Handle SIGHUP, SIGINT, and SIGTERM signals for graceful shutdown."""
    logger.info("Received shutdown signal, stopping Adapters Controller...")
    stop_signal.set()


def run(parent_stop_signal: threading.Event | None = None):
    """Run the Adapters Controller with its control loop."""

    global adapters_controller_monitored

    platform_config = get_platform_config()

    # Create logger after configuration is set up
    logger.debug("Starting adapters controller")

    # Use provided stop signal or create our own
    if parent_stop_signal is None:
        # Register the handler for SIGHUP, SIGINT, and SIGTERM only if running standalone
        signal.signal(signal.SIGHUP, handle_sighup)
        signal.signal(signal.SIGINT, handle_sighup)
        signal.signal(signal.SIGTERM, handle_sighup)
        local_stop_signal = stop_signal
    else:
        local_stop_signal = parent_stop_signal

    logger.debug(f"Initialized NeMo Platform SDK with base_url: {platform_config.base_url}")

    adapters_controller = AdaptersController(stop_signal=local_stop_signal)
    adapters_controller_monitored = TrackLastExecutionTime(adapters_controller)

    nim_peft_refresh_interval = int(os.getenv("NIM_PEFT_REFRESH_INTERVAL", "5"))
    # Create the control loop with configured interval
    adapters_controller_loop = Loop(
        TimedLoopWaiter(nim_peft_refresh_interval, stop_signal=local_stop_signal),
        adapters_controller_monitored,
        stop_signal=local_stop_signal,
    )

    # Register loop with ControllerManager
    controller_manager = ControllerManager.get_instance()
    controller_manager.register("adapters_controller", adapters_controller_loop)

    # Start the control loop
    logger.debug("Starting Adapters Controller control loop...")
    adapters_controller_loop.start()
    logger.debug("Adapters controller started successfully")

    try:
        # Wait for stop signal or control loop to finish
        while not local_stop_signal.is_set():
            local_stop_signal.wait(timeout=1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping adapters controller")
    finally:
        adapters_controller_loop.stop()
        adapters_controller_loop.join()
        logger.info("Adapters controller stopped")


if __name__ == "__main__":
    run()
