"""Core objects mirroring homeassistant.core for the standalone runtime.

Threading model (same rules as Home Assistant):
- There is one asyncio event loop (the "HA loop"). hass.loop is that loop.
- Calls coming from other threads (e.g. the serial reader thread of eltakobus)
  are marshalled into the loop with call_soon_threadsafe /
  run_coroutine_threadsafe. That is what makes hass.bus.fire(),
  hass.create_task() and dispatcher_send() safe to call from anywhere.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

LOGGER = logging.getLogger("homeassistant.shim")


def callback(func):
    """Mark a function as safe to run in the event loop (decorator, no wrapping)."""
    setattr(func, "_hass_callback", True)
    return func


def is_callback(func) -> bool:
    return getattr(func, "_hass_callback", False) is True


@dataclass
class Event:
    event_type: str
    data: dict = field(default_factory=dict)
    time_fired: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {"event_type": self.event_type, "data": self.data,
                "time_fired": self.time_fired.isoformat()}


@dataclass
class ServiceCall:
    domain: str
    service: str
    data: dict = field(default_factory=dict)


class State:
    """State of an entity, compatible with what the integration reads from it."""

    def __init__(self, entity_id: str, state: str, attributes: dict | None = None,
                 last_changed: datetime | None = None, last_updated: datetime | None = None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})
        now = datetime.now(timezone.utc)
        self.last_changed = last_changed or now
        self.last_updated = last_updated or now

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "attributes": self.attributes,
            "last_changed": self.last_changed.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        def _parse(value):
            try:
                return datetime.fromisoformat(value)
            except (TypeError, ValueError):
                return None
        return cls(data["entity_id"], data["state"], data.get("attributes"),
                   _parse(data.get("last_changed")), _parse(data.get("last_updated")))


class EventBus:
    def __init__(self, hass: "HomeAssistant"):
        self._hass = hass
        self._listeners: dict[str, list[Callable]] = {}

    def async_listen(self, event_type: str, listener) -> Callable[[], None]:
        self._listeners.setdefault(event_type, []).append(listener)

        def remove():
            try:
                self._listeners.get(event_type, []).remove(listener)
            except ValueError:
                pass
        return remove

    def async_listen_once(self, event_type: str, listener) -> Callable[[], None]:
        remove_holder = {}

        def once(event):
            remove_holder["remove"]()
            return listener(event)
        remove_holder["remove"] = self.async_listen(event_type, once)
        return remove_holder["remove"]

    def fire(self, event_type: str, event_data: dict | None = None) -> None:
        """Thread-safe fire."""
        self._hass.run_in_loop(self.async_fire, event_type, event_data)

    def async_fire(self, event_type: str, event_data: dict | None = None) -> None:
        event = Event(event_type, event_data or {})
        for listener in list(self._listeners.get(event_type, [])):
            self._hass.invoke_listener(listener, event)


class StateMachine:
    def __init__(self, hass: "HomeAssistant"):
        self._hass = hass
        self._states: dict[str, State] = {}
        self._listeners: list[Callable[[str, State | None, State | None], None]] = []

    def get(self, entity_id: str) -> State | None:
        return self._states.get(entity_id)

    def all(self) -> list[State]:
        return list(self._states.values())

    def async_set(self, entity_id: str, new_state: str, attributes: dict | None = None) -> None:
        old = self._states.get(entity_id)
        state = State(entity_id, str(new_state), attributes,
                      last_changed=old.last_changed if old and old.state == str(new_state) else None)
        self._states[entity_id] = state
        for listener in list(self._listeners):
            try:
                listener(entity_id, old, state)
            except Exception:  # noqa: BLE001 - a listener must not break state writes
                LOGGER.exception("State listener failed for %s", entity_id)
        self._hass.bus.async_fire("state_changed", {
            "entity_id": entity_id, "old_state": old, "new_state": state})

    def async_remove(self, entity_id: str) -> None:
        self._states.pop(entity_id, None)

    def add_listener(self, listener) -> Callable[[], None]:
        """Standalone extension: raw listener(entity_id, old, new). Returns unsubscribe."""
        self._listeners.append(listener)

        def remove():
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass
        return remove


class ServiceRegistry:
    def __init__(self, hass: "HomeAssistant"):
        self._hass = hass
        self._services: dict[tuple[str, str], Callable] = {}

    def async_register(self, domain: str, service: str, service_func, schema=None) -> None:
        self._services[(domain, service)] = service_func

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._services

    def async_services(self) -> dict:
        result: dict[str, dict] = {}
        for (domain, service) in self._services:
            result.setdefault(domain, {})[service] = {}
        return result

    async def async_call(self, domain: str, service: str, service_data: dict | None = None,
                         blocking: bool = True) -> None:
        func = self._services.get((domain, service))
        if func is None:
            raise ValueError(f"Service {domain}.{service} not found")
        call = ServiceCall(domain, service, dict(service_data or {}))
        result = func(call)
        if inspect.isawaitable(result):
            await result


class Config:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.time_zone = time.tzname[0] if time.tzname else "UTC"

    def path(self, *path: str) -> str:
        return os.path.join(self.config_dir, *path)


class HomeAssistant:
    """The tiny hass object the integration code runs against."""

    def __init__(self, config_dir: str, loop: asyncio.AbstractEventLoop | None = None):
        self.loop = loop or asyncio.get_event_loop()
        self.data: dict[str, Any] = {}
        self.config = Config(config_dir)
        self.bus = EventBus(self)
        self.states = StateMachine(self)
        self.services = ServiceRegistry(self)
        self.config_entries = None      # set by the runtime (config_entries.ConfigEntries)
        self.http = None                # set by the runtime (components.http.HomeAssistantHTTP)
        self.is_running = True
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ tasks
    def _track(self, task: asyncio.Task) -> asyncio.Task:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def async_create_task(self, coro, name: str | None = None) -> asyncio.Task:
        """Create a task. Must be called from within the event loop."""
        return self._track(self.loop.create_task(coro, name=name))

    def create_task(self, coro, name: str | None = None):
        """Thread-safe variant: usable from the event loop and from other threads."""
        if self._in_loop():
            return self.async_create_task(coro, name)
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def async_add_job(self, target, *args):
        if asyncio.iscoroutine(target):
            return self.async_create_task(target)
        result = target(*args)
        if inspect.isawaitable(result):
            return self.async_create_task(result)
        return None

    async def async_add_executor_job(self, target, *args):
        return await self.loop.run_in_executor(None, target, *args)

    # -------------------------------------------------------- thread handling
    def _in_loop(self) -> bool:
        try:
            return asyncio.get_running_loop() is self.loop
        except RuntimeError:
            return False

    def run_in_loop(self, func, *args) -> None:
        """Run a sync function in the event loop, from any thread."""
        if self._in_loop():
            func(*args)
        else:
            self.loop.call_soon_threadsafe(func, *args)

    def invoke_listener(self, listener, *args) -> None:
        """Call a sync or async listener from within the loop."""
        try:
            result = listener(*args)
        except Exception:  # noqa: BLE001 - one listener must not stop the others
            LOGGER.exception("Listener %s failed", listener)
            return
        if inspect.isawaitable(result):
            self.async_create_task(result)

    # ------------------------------------------------------------------ stop
    async def async_stop(self) -> None:
        self.is_running = False
        self.bus.async_fire("homeassistant_stop", {})
        # give listeners scheduled as tasks a chance to run
        pending = [task for task in self._tasks if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=5)

    async def async_block_till_done(self, max_rounds: int = 10) -> None:
        # bounded: gateways with auto_reconnect keep scheduling new tasks forever,
        # so "wait until no tasks are pending" must not loop indefinitely.
        for _ in range(max_rounds):
            pending = [task for task in self._tasks if not task.done()
                       and task is not asyncio.current_task()]
            if not pending:
                return
            await asyncio.wait(pending, timeout=10)


# HassJob is referenced by some helper signatures; provide a stand-in.
class HassJob:
    def __init__(self, target):
        self.target = target
