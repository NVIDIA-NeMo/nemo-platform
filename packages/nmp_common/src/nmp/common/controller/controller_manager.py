# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Controller manager for registering and managing control loops."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from logging import getLogger
from threading import RLock, local
from typing import Dict, Optional, Self

from .controller import Loop

logger = getLogger(__name__)


class ControllerManager:
    """Singleton manager for registering control loops and validating their health.

    Example usage:
        manager = ControllerManager.get_instance()
        manager.register("my_loop", my_loop_instance)

        # Check if all loops are healthy
        all_healthy, status = manager.validate_all_healthy()
        if not all_healthy:
            logger.error(f"Unhealthy loops: {status}")
    """

    _instance: Optional[Self] = None
    _instance_lock = RLock()

    def __init__(self):
        """Private constructor. Use get_instance() to get the singleton instance."""
        if ControllerManager._instance is not None:
            raise RuntimeError("Use ControllerManager.get_instance() to get the singleton instance")
        self._init_state()

    def _init_state(self) -> None:
        """Initialize mutable singleton state."""
        self._loops: Dict[str, Loop] = {}
        self._reported_health: Dict[str, bool] = {}
        self._controllers_awaiting_registration: set[str] = set()
        self._registered_controllers: set[str] = set()
        self._controller_loops: Dict[str, set[str]] = {}
        self._loop_controllers: Dict[str, str] = {}
        self._controller_context = local()
        self._lock = RLock()

    @classmethod
    def get_instance(cls) -> "ControllerManager":
        """Get the singleton instance of ControllerManager.

        Returns:
            The singleton ControllerManager instance.
        """
        with cls._instance_lock:
            if cls._instance is None:
                instance = cls.__new__(cls)
                instance._init_state()
                cls._instance = instance
        return cls._instance

    def await_controller_registration(self, name: str) -> None:
        """Track a runner-owned controller until it registers at least one loop."""
        with self._lock:
            self._controllers_awaiting_registration.add(name)
            self._registered_controllers.discard(name)

    def mark_controller_failed(self, name: str) -> None:
        """Record an unexpected exit as a missing controller registration."""
        self.await_controller_registration(name)

    def stop_tracking_controller(self, name: str) -> None:
        """Remove controller state unless one of its loops is still running."""
        with self._lock:
            still_running = {
                loop_name
                for loop_name in self._controller_loops.get(name, set())
                if isinstance((loop := self._loops.get(loop_name)), threading.Thread) and loop.is_alive()
            }
            if still_running:
                logger.warning(
                    "Leaving health tracking in place for %r; loop(s) %s still running",
                    name,
                    sorted(still_running),
                )
                return

            self._controllers_awaiting_registration.discard(name)
            self._registered_controllers.discard(name)
            self._reported_health.pop(name, None)
            for loop_name in self._controller_loops.pop(name, set()):
                self._loop_controllers.pop(loop_name, None)
                self._loops.pop(loop_name, None)
                self._reported_health.pop(loop_name, None)

    @contextmanager
    def controller_registration_context(self, name: str) -> Iterator[None]:
        """Associate loop registrations in the current thread with a controller."""
        previous = getattr(self._controller_context, "name", None)
        self._controller_context.name = name
        try:
            yield
        finally:
            self._controller_context.name = previous

    def register(self, name: str, loop: Loop) -> None:
        """Register a control loop with a unique name.

        The registration name is used as the loop's thread name for debugging
        and observability context (traces/logs).

        Args:
            name: Unique identifier for the loop (also used as thread name).
            loop: Loop instance to register.

        Raises:
            ValueError: If a loop with this name is already registered.
        """
        with self._lock:
            if name in self._loops:
                raise ValueError(f"Loop with name '{name}' is already registered")
            loop.name = name
            self._loops[name] = loop
            controller_name = getattr(self._controller_context, "name", None)
            if controller_name is not None:
                self._controller_loops.setdefault(controller_name, set()).add(name)
                self._loop_controllers[name] = controller_name
                if controller_name in self._controllers_awaiting_registration:
                    self._registered_controllers.add(controller_name)
        logger.debug(f"Registered loop: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a loop by name.

        Args:
            name: Name of the loop to unregister.

        Raises:
            KeyError: If no loop with this name is registered.
        """
        with self._lock:
            if name not in self._loops:
                raise KeyError(f"No loop with name '{name}' is registered")
            del self._loops[name]
            self._reported_health.pop(name, None)
            controller_name = self._loop_controllers.pop(name, None)
            if controller_name is not None:
                controller_loops = self._controller_loops[controller_name]
                controller_loops.discard(name)
                if not controller_loops:
                    del self._controller_loops[controller_name]
                    self._registered_controllers.discard(controller_name)
        logger.info(f"Unregistered loop: {name}")

    def get_loop(self, name: str) -> Loop:
        """Get a registered loop by name.

        Args:
            name: Name of the loop to retrieve.

        Returns:
            The registered Loop instance.

        Raises:
            KeyError: If no loop with this name is registered.
        """
        with self._lock:
            if name not in self._loops:
                raise KeyError(f"No loop with name '{name}' is registered")
            return self._loops[name]

    def get_all_loops(self) -> Dict[str, Loop]:
        """Get all registered loops.

        Returns:
            Dictionary mapping loop names to Loop instances.
        """
        with self._lock:
            return self._loops.copy()

    def validate_all_healthy(self, detailed: bool = True) -> tuple[bool, Dict[str, bool]]:
        """Validate that all registered loops are healthy.

        Checks the is_healthy property on each loop. Loops without
        an is_healthy property are considered healthy by default.

        Args:
            detailed: If True, returns detailed status for each loop.
                     If False, only returns overall health status with empty dict.

        Returns:
            A tuple containing:
            - bool: True if all loops are healthy, False otherwise.
            - Dict[str, bool]: Mapping of loop names to their health status
                              (only if detailed=True, otherwise empty dict).
        """
        with self._lock:
            loops = self._loops.copy()
            missing_controllers = self._controllers_awaiting_registration - self._registered_controllers
            # Owned loops distinguish startup failures from later exits.
            previously_registered = {name for name in missing_controllers if self._controller_loops.get(name)}

        if not loops and not missing_controllers:
            logger.debug("No loops registered for health validation")
            return True, {}

        health_status = {name: False for name in sorted(missing_controllers)} if detailed else {}
        all_healthy = not missing_controllers

        for name in missing_controllers:
            reason = (
                "controller exited unexpectedly after registering a control loop"
                if name in previously_registered
                else "controller has not registered a control loop"
            )
            self._log_health_transition(name, False, reason)

        for name, loop in loops.items():
            # Runner-level failure takes precedence over a same-named loop.
            if name in missing_controllers:
                continue
            # Check if loop has is_healthy property (duck typing)
            if hasattr(loop, "is_healthy"):
                try:
                    is_healthy = loop.is_healthy
                    if detailed:
                        health_status[name] = is_healthy
                    if not is_healthy:
                        all_healthy = False
                        logger.debug(f"Loop '{name}' is unhealthy")
                    self._log_health_transition(name, is_healthy, getattr(loop, "unhealthy_reason", None))
                except Exception as e:
                    if detailed:
                        health_status[name] = False
                    all_healthy = False
                    logger.error(f"Error checking health of loop '{name}': {e}", exc_info=True)
                    self._log_health_transition(name, False, f"health check raised: {e}")
            else:
                # No is_healthy property, assume healthy
                if detailed:
                    health_status[name] = True
                logger.debug(f"Loop '{name}' does not implement is_healthy, assuming healthy")

        return all_healthy, health_status if detailed else {}

    def _log_health_transition(self, name: str, is_healthy: bool, reason: str | None) -> None:
        """Log only when a loop's health changes.

        Health is evaluated on every readiness probe, so logging each unhealthy
        evaluation would be far too noisy to be useful. Reporting the edges makes
        the loop responsible for a degraded process identifiable from the logs
        alone.
        """
        with self._lock:
            previous = self._reported_health.get(name)
            if previous == is_healthy:
                return
            self._reported_health[name] = is_healthy

            if is_healthy:
                if previous is not None:
                    logger.info(f"Control loop '{name}' is healthy again")
            else:
                logger.warning(f"Control loop '{name}' is unhealthy: {reason or 'reason unavailable'}")

    def clear(self) -> None:
        """Clear all registered loops.

        This method is primarily useful for testing purposes.
        """
        with self._lock:
            count = len(self._loops)
            self._loops.clear()
            self._reported_health.clear()
            self._controllers_awaiting_registration.clear()
            self._registered_controllers.clear()
            self._controller_loops.clear()
            self._loop_controllers.clear()
        logger.info(f"Cleared {count} registered loop(s)")
