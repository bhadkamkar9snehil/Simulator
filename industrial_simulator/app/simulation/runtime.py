from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.config_store import CONFIG_DIR, ensure_dir

from .contracts import SimulationSource, SimulationTarget
from .interfaces import InterfaceHostManager, create_target
from .mapping import map_frame, map_schema
from .models import (
    RuntimeSnapshot,
    SignalDefinition,
    SimulationDefinition,
    SimulationFrame,
    SimulationStatus,
    TargetBinding,
    TargetRuntimeStatus,
    WorldDefinition,
    utc_now_iso,
)
from .sources import create_source

log = logging.getLogger("industrial.unified_runtime")


class _FrameClock:
    def __init__(self, definition: SimulationDefinition):
        self.spec = definition.clock
        self.previous_source_time: datetime | None = None
        self.first = True

    def reset(self) -> None:
        self.previous_source_time = None
        self.first = True

    async def wait(self, frame: SimulationFrame) -> None:
        current = _parse_timestamp(frame.source_timestamp)
        if self.first:
            self.first = False
            self.previous_source_time = current
            return
        delay = 1.0 / (self.spec.frequency_hz * self.spec.speed)
        if self.spec.mode == "source_timestamp" and current and self.previous_source_time:
            source_delay = (current - self.previous_source_time).total_seconds()
            if source_delay > 0:
                delay = source_delay / self.spec.speed
        self.previous_source_time = current
        await asyncio.sleep(min(max(delay, 0.001), self.spec.max_delay_seconds))


class _TargetRunner:
    def __init__(self, target: SimulationTarget, binding: TargetBinding, on_fatal: Callable[[str, str], None]):
        self.target = target
        self.binding = binding
        self.on_fatal = on_fatal
        self.queue: asyncio.Queue[SimulationFrame] = asyncio.Queue(maxsize=binding.queue_size)
        self.task: asyncio.Task[None] | None = None
        self.started = False
        self.simulation_id = ""
        self.simulation_name = ""
        self.schema: list[SignalDefinition] = []
        self.last_error: str | None = None
        self.dropped_frames = 0
        self.published_frames = 0

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        self.simulation_id = simulation_id
        self.simulation_name = simulation_name
        self.schema = schema
        try:
            await self.target.start(simulation_id, simulation_name, schema)
            self.started = True
        except Exception as exc:
            self.last_error = str(exc)
            if self.binding.failure_policy == "stop_simulation":
                raise
        self.task = asyncio.create_task(self._run(), name=f"target:{simulation_id}:{self.binding.target_id}")

    async def enqueue(self, frame: SimulationFrame) -> None:
        if self.binding.overflow_policy == "block":
            await self.queue.put(frame)
            return
        if not self.queue.full():
            self.queue.put_nowait(frame)
            return
        if self.binding.overflow_policy == "drop_newest":
            self.dropped_frames += 1
            return
        try:
            self.queue.get_nowait()
            self.queue.task_done()
        except asyncio.QueueEmpty:
            pass
        self.dropped_frames += 1
        self.queue.put_nowait(frame)

    async def drain(self) -> None:
        await self.queue.join()

    async def stop(self) -> None:
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.target.stop()
        self.started = False

    def status(self) -> TargetRuntimeStatus:
        status = self.target.status()
        status.queue_depth = self.queue.qsize()
        status.dropped_frames = self.dropped_frames
        status.published_frames = self.published_frames
        if self.last_error:
            status.last_error = self.last_error
            if status.state == "running":
                status.state = "error"
        return status

    async def _run(self) -> None:
        while True:
            frame = await self.queue.get()
            try:
                if not self.started:
                    await self.target.start(self.simulation_id, self.simulation_name, self.schema)
                    self.started = True
                await self.target.publish(frame)
                self.published_frames += 1
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                await self._reset_target()
                if self.binding.failure_policy == "stop_simulation":
                    self.on_fatal(self.binding.target_id, self.last_error)
                elif self.binding.failure_policy == "retry":
                    await asyncio.sleep(self.binding.retry_seconds)
            finally:
                self.queue.task_done()

    async def _reset_target(self) -> None:
        try:
            await self.target.stop()
        except Exception:
            log.exception("Failed resetting target %s.", self.binding.target_id)
        self.started = False


class SimulationInstance:
    def __init__(self, definition: SimulationDefinition, hosts: InterfaceHostManager):
        self.definition = definition
        self.hosts = hosts
        self.state = "created"
        self.source: SimulationSource | None = None
        self.runners: list[_TargetRunner] = []
        self.task: asyncio.Task[None] | None = None
        self.run_gate = asyncio.Event()
        self.run_gate.set()
        self.lifecycle_lock = asyncio.Lock()
        self.clock = _FrameClock(definition)
        self.emitted_count = 0
        self.started_at: str | None = None
        self.updated_at: str | None = None
        self.last_error: str | None = None
        self.last_frame: SimulationFrame | None = None
        self.last_target_statuses: list[TargetRuntimeStatus] = []
        self.last_source_position = 0
        self.last_source_count: int | None = None
        self.start_position = 0
        self.direction = 1
        self.fatal_error: str | None = None

    async def start(self) -> SimulationStatus:
        async with self.lifecycle_lock:
            if self.state in {"running", "paused"}:
                return self.status()
            await self._close_resources()
            self._reset_run_state()
            self.state = "starting"
            try:
                self.source = create_source(self.definition.source, self.definition.simulation_id)
                await self.source.open()
                schema = map_schema(
                    self.source.schema(),
                    self.definition.mappings,
                    self.definition.drop_unmapped_signals,
                )
                if not schema:
                    raise ValueError("Simulation mapping produced an empty signal schema.")
                self.start_position = self.source.position
                self.runners = self._build_runners()
                for runner in self.runners:
                    await runner.start(self.definition.simulation_id, self.definition.name, schema)
                self.state = "running"
                self.started_at = self.updated_at = utc_now_iso()
                self.task = asyncio.create_task(self._run(), name=f"simulation:{self.definition.simulation_id}")
            except Exception as exc:
                self.state = "error"
                self.last_error = str(exc)
                await self._close_resources()
                raise
            return self.status()

    async def pause(self) -> SimulationStatus:
        async with self.lifecycle_lock:
            if self.state == "running":
                self.state = "paused"
                self.run_gate.clear()
                self.updated_at = utc_now_iso()
            return self.status()

    async def resume(self) -> SimulationStatus:
        async with self.lifecycle_lock:
            if self.state == "paused":
                self.state = "running"
                self.run_gate.set()
                self.updated_at = utc_now_iso()
            return self.status()

    async def stop(self) -> SimulationStatus:
        async with self.lifecycle_lock:
            task, self.task = self.task, None
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._close_resources()
            if self.state != "completed":
                self.state = "stopped"
            self.run_gate.set()
            self.updated_at = utc_now_iso()
            return self.status()

    def status(self) -> SimulationStatus:
        targets = [runner.status() for runner in self.runners] if self.runners else list(self.last_target_statuses)
        visible_state = "degraded" if self.state == "running" and any(item.state == "error" for item in targets) else self.state
        return SimulationStatus(
            simulation_id=self.definition.simulation_id,
            name=self.definition.name,
            state=visible_state,  # type: ignore[arg-type]
            world_id=self.definition.world_id,
            emitted_count=self.emitted_count,
            source_position=self.source.position if self.source else self.last_source_position,
            source_count=self.source.count if self.source else self.last_source_count,
            started_at=self.started_at,
            updated_at=self.updated_at,
            last_error=self.last_error,
            targets=targets,
        )

    def _reset_run_state(self) -> None:
        self.last_error = None
        self.fatal_error = None
        self.emitted_count = 0
        self.last_frame = None
        self.last_target_statuses = []
        self.last_source_position = 0
        self.last_source_count = None
        self.direction = 1
        self.clock.reset()
        self.run_gate.set()

    def _build_runners(self) -> list[_TargetRunner]:
        return [
            _TargetRunner(create_target(binding, self.hosts), binding, self._target_fatal)
            for binding in self.definition.targets
            if binding.enabled
        ]

    async def _run(self) -> None:
        try:
            while self.state in {"running", "paused"}:
                await self.run_gate.wait()
                if self.state != "running":
                    continue
                if self.fatal_error:
                    raise RuntimeError(self.fatal_error)
                frame = await self._next_frame()
                if frame is None:
                    await asyncio.gather(*(runner.drain() for runner in self.runners))
                    self.state = "completed"
                    self.updated_at = utc_now_iso()
                    break
                await self.clock.wait(frame)
                frame = self._decorate_frame(frame)
                self.last_frame = frame
                await asyncio.gather(*(runner.enqueue(frame) for runner in self.runners))
                self.emitted_count += 1
                self.updated_at = frame.timestamp
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = "error"
            self.last_error = str(exc)
            self.updated_at = utc_now_iso()
            log.exception("Unified simulation %s failed.", self.definition.simulation_id)
        finally:
            await self._close_resources()

    def _decorate_frame(self, frame: SimulationFrame) -> SimulationFrame:
        mapped = map_frame(frame, self.definition.mappings, self.definition.drop_unmapped_signals)
        context = dict(mapped.context)
        if self.definition.world_id:
            context.setdefault("world_id", self.definition.world_id)
        return mapped.model_copy(update={
            "sequence": self.emitted_count,
            "timestamp": utc_now_iso(),
            "context": context,
        })

    async def _next_frame(self) -> SimulationFrame | None:
        source = self.source
        if source is None:
            return None
        if self.direction < 0:
            return await self._previous_frame(source)
        frame = await source.next_frame()
        if frame is not None:
            return frame
        mode = self.definition.loop_mode
        if mode == "once":
            return None
        if mode == "hold_last":
            return self.last_frame.model_copy(update={"timestamp": utc_now_iso()}) if self.last_frame else None
        if mode == "loop_forever":
            await source.seek(self.start_position)
            self.clock.reset()
            return await source.next_frame()
        count = source.count
        if count is None or count <= self.start_position + 1:
            return self.last_frame.model_copy(update={"timestamp": utc_now_iso()}) if self.last_frame else None
        self.direction = -1
        await source.seek(count - 2)
        return await source.next_frame()

    async def _previous_frame(self, source: SimulationSource) -> SimulationFrame | None:
        previous_index = source.position - 2
        if previous_index >= self.start_position:
            await source.seek(previous_index)
            return await source.next_frame()
        self.direction = 1
        next_index = self.start_position + 1
        if source.count is not None and next_index >= source.count:
            next_index = self.start_position
        await source.seek(next_index)
        return await source.next_frame()

    def _target_fatal(self, target_id: str, error: str) -> None:
        self.fatal_error = f"Target {target_id} failed: {error}"

    async def _close_resources(self) -> None:
        runners, self.runners = self.runners, []
        if runners:
            await asyncio.gather(*(self._stop_runner(runner) for runner in runners))
            self.last_target_statuses = [runner.status() for runner in runners]
        source, self.source = self.source, None
        if source is not None:
            self.last_source_position = source.position
            self.last_source_count = source.count
            try:
                await source.close()
            except Exception:
                log.exception("Failed closing source for %s.", self.definition.simulation_id)

    async def _stop_runner(self, runner: _TargetRunner) -> None:
        try:
            await runner.stop()
        except Exception:
            log.exception("Failed stopping target %s.", runner.binding.target_id)


class SimulationManager:
    def __init__(self, state_path: Path | None = None):
        ensure_dir()
        self.state_path = state_path or (CONFIG_DIR / "unified_simulations.json")
        self.hosts = InterfaceHostManager()
        self.definitions: dict[str, SimulationDefinition] = {}
        self.worlds: dict[str, WorldDefinition] = {}
        self.instances: dict[str, SimulationInstance] = {}
        self.persistence_error: str | None = None
        self.lock = asyncio.Lock()
        self._load()

    async def create(self, definition: SimulationDefinition) -> SimulationStatus:
        async with self.lock:
            if definition.simulation_id in self.definitions:
                raise ValueError(f"Simulation already exists: {definition.simulation_id}")
            self.definitions[definition.simulation_id] = definition
            self._save()
        return await self.start(definition.simulation_id) if definition.autostart else self._created_status(definition)

    async def replace(self, simulation_id: str, definition: SimulationDefinition) -> SimulationStatus:
        if simulation_id != definition.simulation_id:
            raise ValueError("Path simulation id must match definition.simulation_id.")
        instance = self.instances.get(simulation_id)
        if instance and instance.state in {"running", "paused", "starting"}:
            raise ValueError("Stop a simulation before replacing its definition.")
        async with self.lock:
            if simulation_id not in self.definitions:
                raise KeyError(simulation_id)
            self.definitions[simulation_id] = definition
            self.instances.pop(simulation_id, None)
            self._save()
        return self._created_status(definition)

    async def delete(self, simulation_id: str) -> None:
        instance = self.instances.pop(simulation_id, None)
        if instance:
            await instance.stop()
        async with self.lock:
            if simulation_id not in self.definitions:
                raise KeyError(simulation_id)
            self.definitions.pop(simulation_id)
            for world in self.worlds.values():
                world.simulation_ids = [item for item in world.simulation_ids if item != simulation_id]
            self._save()

    async def start(self, simulation_id: str) -> SimulationStatus:
        definition = self._definition(simulation_id)
        instance = self.instances.get(simulation_id)
        if instance is None:
            instance = self.instances[simulation_id] = SimulationInstance(definition, self.hosts)
        return await instance.start()

    async def pause(self, simulation_id: str) -> SimulationStatus:
        return await self._instance(simulation_id).pause()

    async def resume(self, simulation_id: str) -> SimulationStatus:
        return await self._instance(simulation_id).resume()

    async def stop(self, simulation_id: str) -> SimulationStatus:
        return await self._instance(simulation_id).stop()

    def get_definition(self, simulation_id: str) -> SimulationDefinition:
        return self._definition(simulation_id)

    def list_definitions(self) -> list[SimulationDefinition]:
        return list(self.definitions.values())

    def status(self, simulation_id: str) -> SimulationStatus:
        definition = self._definition(simulation_id)
        instance = self.instances.get(simulation_id)
        return instance.status() if instance else self._created_status(definition)

    def list_status(self) -> list[SimulationStatus]:
        return [self.status(simulation_id) for simulation_id in self.definitions]

    def http_frame(self, simulation_id: str, target_id: str) -> SimulationFrame | None:
        definition = self._definition(simulation_id)
        matches = [item for item in definition.targets if item.target_id == target_id and item.kind in {"http", "http_stream"}]
        if not matches:
            raise KeyError(target_id)
        instance = self.instances.get(simulation_id)
        return instance.last_frame if instance else None

    def snapshot(self, simulation_id: str) -> dict[str, Any]:
        instance = self.instances.get(simulation_id)
        frame = instance.last_frame.model_dump() if instance and instance.last_frame else None
        return {"simulation_id": simulation_id, "frame": frame, "status": self.status(simulation_id).model_dump()}

    async def create_world(self, world: WorldDefinition) -> WorldDefinition:
        self._validate_world_members(world)
        async with self.lock:
            if world.world_id in self.worlds:
                raise ValueError(f"World already exists: {world.world_id}")
            self.worlds[world.world_id] = world
            self._save()
        return world

    async def replace_world(self, world_id: str, world: WorldDefinition) -> WorldDefinition:
        if world_id != world.world_id:
            raise ValueError("Path world id must match world.world_id.")
        self._validate_world_members(world)
        async with self.lock:
            if world_id not in self.worlds:
                raise KeyError(world_id)
            self.worlds[world_id] = world
            self._save()
        return world

    async def delete_world(self, world_id: str) -> None:
        async with self.lock:
            if world_id not in self.worlds:
                raise KeyError(world_id)
            self.worlds.pop(world_id)
            self._save()

    async def start_world(self, world_id: str) -> list[SimulationStatus]:
        world = self._world(world_id)
        return await asyncio.gather(*(self.start(simulation_id) for simulation_id in world.simulation_ids))

    async def stop_world(self, world_id: str) -> list[SimulationStatus]:
        world = self._world(world_id)
        results: list[SimulationStatus] = []
        for simulation_id in world.simulation_ids:
            instance = self.instances.get(simulation_id)
            results.append(await instance.stop() if instance else self.status(simulation_id))
        return results

    def runtime_snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            simulations=self.list_status(),
            worlds=list(self.worlds.values()),
            persistence_error=self.persistence_error,
        )

    def interface_status(self) -> dict[str, Any]:
        return self.hosts.status()

    async def shutdown(self) -> None:
        for instance in list(self.instances.values()):
            try:
                await instance.stop()
            except Exception:
                log.exception("Failed stopping simulation %s.", instance.definition.simulation_id)
        await self.hosts.shutdown()

    def _definition(self, simulation_id: str) -> SimulationDefinition:
        definition = self.definitions.get(simulation_id)
        if definition is None:
            raise KeyError(simulation_id)
        return definition

    def _instance(self, simulation_id: str) -> SimulationInstance:
        self._definition(simulation_id)
        instance = self.instances.get(simulation_id)
        if instance is None:
            raise ValueError("Simulation has not been started.")
        return instance

    def _world(self, world_id: str) -> WorldDefinition:
        world = self.worlds.get(world_id)
        if world is None:
            raise KeyError(world_id)
        return world

    def _validate_world_members(self, world: WorldDefinition) -> None:
        missing = [item for item in world.simulation_ids if item not in self.definitions]
        if missing:
            raise ValueError(f"World references unknown simulations: {', '.join(missing)}")

    @staticmethod
    def _created_status(definition: SimulationDefinition) -> SimulationStatus:
        return SimulationStatus(
            simulation_id=definition.simulation_id,
            name=definition.name,
            state="created",
            world_id=definition.world_id,
        )

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            definitions = [SimulationDefinition.model_validate(item) for item in payload.get("simulations", [])]
            worlds = [WorldDefinition.model_validate(item) for item in payload.get("worlds", [])]
            self.definitions = {item.simulation_id: item for item in definitions}
            self.worlds = {item.world_id: item for item in worlds}
        except Exception as exc:
            self.persistence_error = str(exc)
            log.exception("Could not load unified simulator state from %s.", self.state_path)

    def _save(self) -> None:
        ensure_dir()
        payload = {
            "version": 1,
            "simulations": [item.model_dump(mode="json") for item in self.definitions.values()],
            "worlds": [item.model_dump(mode="json") for item in self.worlds.values()],
        }
        temp_path = self.state_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.replace(self.state_path)
            self.persistence_error = None
        except Exception as exc:
            self.persistence_error = str(exc)
            raise


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None


simulation_manager = SimulationManager()
