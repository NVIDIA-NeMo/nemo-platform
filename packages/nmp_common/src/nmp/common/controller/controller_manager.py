# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Controller manager for registering and managing control loops."""

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

    def __init__(self):
        """Private constructor. Use get_instance() to get the singleton instance."""
        if ControllerManager._instance is not None:
            raise RuntimeError("Use ControllerManager.get_instance() to get the singleton instance")
        self._loops: Dict[str, Loop] = {}
        self._reported_health: Dict[str, bool] = {}
        self._expected_controllers: set[str] = set()
        self._registered_controllers: set[str] = set()
        self._failed_controllers: set[str] = set()
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
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._loops = {}
            cls._instance._reported_health = {}
            cls._instance._expected_controllers = set()
            cls._instance._registered_controllers = set()
            cls._instance._failed_controllers = set()
            cls._instance._controller_loops = {}
            cls._instance._loop_controllers = {}
            cls._instance._controller_context = local()
            cls._instance._lock = RLock()
        return cls._instance

    def expect_controller(self, name: str) -> None:
        """Declare a runner-owned controller that must register at least one loop."""
        with self._lock:
            self._expected_controllers.add(name)
            self._registered_controllers.discard(name)
            self._failed_controllers.discard(name)

    def mark_controller_failed(self, name: str) -> None:
        """Record that a runner-owned controller exited unexpectedly."""
        with self._lock:
            self._expected_controllers.add(name)
            self._registered_controllers.discard(name)
            self._failed_controllers.add(name)

    def stop_expecting_controller(self, name: str) -> None:
        """Remove runner-owned controller state during platform shutdown."""
        with self._lock:
            self._expected_controllers.discard(name)
            self._registered_controllers.discard(name)
            self._failed_controllers.discard(name)
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
            if controller_name in self._expected_controllers:
                self._registered_controllers.add(controller_name)
                self._controller_loops.setdefault(controller_name, set()).add(name)
                self._loop_controllers[name] = controller_name
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
            missing_controllers = self._expected_controllers - self._registered_controllers
            missing_controllers.update(self._failed_controllers)

        if not loops and not missing_controllers:
            logger.debug("No loops registered for health validation")
            return True, {}

        health_status = {name: False for name in sorted(missing_controllers)} if detailed else {}
        all_healthy = not missing_controllers

        for name in missing_controllers:
            self._log_health_transition(name, False, "controller has not registered a control loop")

        for name, loop in loops.items():
            # Runner-level startup/exit failure takes precedence when a
            # controller and its registered loop use the same name.
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
            self._expected_controllers.clear()
            self._registered_controllers.clear()
            self._failed_controllers.clear()
            self._controller_loops.clear()
            self._loop_controllers.clear()
        logger.info(f"Cleared {count} registered loop(s)")
