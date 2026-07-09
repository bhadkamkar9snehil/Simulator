from __future__ import annotations

import asyncio
import re
import threading
from typing import Any

from app import csv_manager
from app.models import ReplayConfig, ReplayFilesConfig, ReplayFileSelection, CurrentValuesResponse, utc_now_iso
from app.simulator import SimulatorEngine
from app.protocol_adapter import DualProtocolAdapter, ProtocolChannelAdapter, ReplayJobProtocolAdapter


def _safe_prefix(filename: str) -> str:
    stem = filename.rsplit('.', 1)[0]
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_")
    return stem or "file"


def _selection_key(item: ReplayFileSelection) -> tuple[str, str]:
    return (item.source, item.filename)


def _merge_file_selections(*groups: list[ReplayFileSelection]) -> list[ReplayFileSelection]:
    """Merge file selections while preserving UI order and removing duplicates."""
    merged: list[ReplayFileSelection] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for item in group:
            key = _selection_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _tag_selection_map(request: ReplayFilesConfig) -> dict[tuple[str, str, str, str], bool]:
    """Map (protocol, source, filename, csv_column) -> enabled.

    Older requests do not include tag selections. Missing entries are treated as
    enabled to preserve backwards-compatible behavior.
    """
    return {
        (item.protocol, item.source, item.filename, item.csv_column): bool(item.enabled)
        for item in request.tag_selections
    }


def _enabled_count(tags: list[Any]) -> int:
    return len([tag for tag in tags if tag.enabled])


class MultiSimulatorEngine:
    PROTOCOL_START_TIMEOUT_SECONDS = 15.0

    def __init__(self, adapter: DualProtocolAdapter):
        self.adapter = adapter
        self.engines: list[SimulatorEngine] = []
        self.configs: list[ReplayConfig] = []
        self.job_ids: list[str | None] = []
        self.state = "idle"
        self.protocol: str | None = None
        self.last_error: str | None = None
        self.assignment_mode: str = "shared"
        self._runtime_lock = threading.RLock()

    def _start_error_message(self, exc: Exception, action: str) -> str:
        if isinstance(exc, asyncio.TimeoutError):
            return f"{action} timed out after {self.PROTOCOL_START_TIMEOUT_SECONDS:.0f}s. Check whether the OPC UA or MQTT port is already in use."
        return str(exc) or f"{action} failed."

    async def _wait_protocol(self, awaitable: Any, action: str) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=self.PROTOCOL_START_TIMEOUT_SECONDS)
        except Exception as exc:
            message = self._start_error_message(exc, action)
            self.last_error = message
            raise RuntimeError(message) from exc

    def _build_configs_for_files(
        self,
        request: ReplayFilesConfig,
        files: list[ReplayFileSelection],
        protocol: str,
    ) -> tuple[list[ReplayConfig], list[Any], int, list[dict[str, Any]]]:
        configs: list[ReplayConfig] = []
        all_tags = []
        skipped_files: list[dict[str, Any]] = []
        selection_map = _tag_selection_map(request)

        for item in files:
            meta = csv_manager.metadata(item.filename, item.source)
            prefix = _safe_prefix(item.filename)
            tags = []
            for tag in meta.default_tag_mappings:
                new_tag = tag.model_copy(deep=True)
                new_tag.tag_name = f"{prefix}_{new_tag.tag_name}"
                new_tag.node_id = f"{request.node_id_prefix}.{prefix}.{new_tag.node_id.split('.')[-1]}"
                selected = selection_map.get((protocol, item.source, item.filename, tag.csv_column))
                if selected is not None:
                    new_tag.enabled = selected
                tags.append(new_tag)

            enabled_tags = _enabled_count(tags)
            if enabled_tags == 0:
                skipped_files.append({"filename": item.filename, "source": item.source, "protocol": protocol, "reason": "no enabled tags"})
                continue

            all_tags.extend(tags)
            cfg = ReplayConfig(
                protocol=protocol,  # type: ignore[arg-type]
                csv_file=item.filename,
                csv_source=item.source,
                frequency_hz=item.frequency_hz if item.frequency_hz is not None else request.frequency_hz,
                loop_mode=item.loop_mode or request.loop_mode,
                timestamp_mode=item.timestamp_mode or request.timestamp_mode,
                start_row=item.start_row if item.start_row is not None else request.start_row,
                namespace_uri=request.namespace_uri,
                root_folder=request.root_folder,
                node_id_prefix=request.node_id_prefix,
                max_rows=item.max_rows if item.max_rows is not None else request.max_rows,
                mqtt_host=request.mqtt_host,
                mqtt_port=request.mqtt_port,
                mqtt_topic_prefix=request.mqtt_topic_prefix,
                mqtt_device_id=request.mqtt_device_id,
                mqtt_client_id=request.mqtt_client_id,
                mqtt_username=request.mqtt_username,
                mqtt_password=request.mqtt_password,
                mqtt_qos=request.mqtt_qos,
                mqtt_retain=request.mqtt_retain,
                publish_individual_tags=request.publish_individual_tags,
                publish_aggregate=request.publish_aggregate,
                tags=tags,
            )
            configs.append(cfg)

        return configs, all_tags, _enabled_count(all_tags), skipped_files

    async def _configure_protocol_group(
        self,
        request: ReplayFilesConfig,
        files: list[ReplayFileSelection],
        protocol: str,
    ) -> tuple[list[SimulatorEngine], list[ReplayConfig], int, list[dict[str, Any]]]:
        if not files:
            return [], [], 0, []
        configs, all_tags, enabled_tags, skipped_files = self._build_configs_for_files(request, files, protocol)
        if not configs:
            return [], [], 0, skipped_files
        combined = configs[0].model_copy(deep=True)
        combined.tags = all_tags
        publisher = ProtocolChannelAdapter(self.adapter, protocol)
        await self._wait_protocol(publisher.configure_tags(combined), f"{protocol.upper()} configuration")
        engines = [SimulatorEngine(publisher) for _ in configs]
        for engine, cfg in zip(engines, configs):
            await engine.configure(cfg, configure_adapter=False)
        return engines, configs, enabled_tags, skipped_files

    async def configure_files(self, request: ReplayFilesConfig) -> dict[str, Any]:
        await self.stop()

        if request.protocol == "both":
            # BOTH mode is always handled as two explicit protocol plans:
            #   OPC UA plan = Shared files + OPC UA files
            #   MQTT plan   = Shared files + MQTT files
            # This keeps MQTT data separate from OPC UA data while allowing
            # per-protocol tag selection before start.
            opcua_plan = _merge_file_selections(request.files, request.opcua_files)
            mqtt_plan = _merge_file_selections(request.files, request.mqtt_files)
            if not opcua_plan or not mqtt_plan:
                raise ValueError("BOTH mode requires at least one file in the OPC UA plan and at least one file in the MQTT plan. Use Shared files to feed both protocols, or choose OPC UA and MQTT files separately.")

            opc_engines, opc_configs, opc_tags, opc_skipped = await self._configure_protocol_group(request, opcua_plan, "opcua")
            mqtt_engines, mqtt_configs, mqtt_tags, mqtt_skipped = await self._configure_protocol_group(request, mqtt_plan, "mqtt")
            if not opc_engines:
                raise ValueError("No OPC UA tags are enabled. Select at least one OPC UA tag before applying the plan.")
            if not mqtt_engines:
                raise ValueError("No MQTT tags are enabled. Select at least one MQTT tag before applying the plan.")

            self.engines = opc_engines + mqtt_engines
            self.configs = opc_configs + mqtt_configs
            self.job_ids = [None] * len(self.engines)
            self.protocol = "both"
            self.assignment_mode = "separate"
            self.state = "configured"
            self.last_error = None
            return {
                "status": "configured",
                "protocol": "both",
                "assignment_mode": "separate",
                "opcua_file_count": len(opc_configs),
                "mqtt_file_count": len(mqtt_configs),
                "file_count": len(self.configs),
                "tag_count": opc_tags + mqtt_tags,
                "opcua_tag_count": opc_tags,
                "mqtt_tag_count": mqtt_tags,
                "opcua_files": [c.csv_file for c in opc_configs],
                "mqtt_files": [c.csv_file for c in mqtt_configs],
                "skipped_files": opc_skipped + mqtt_skipped,
                "endpoint": self.adapter.get_endpoint(),
            }

        if request.protocol == "opcua":
            files = _merge_file_selections(request.files, request.opcua_files)
        elif request.protocol == "mqtt":
            files = _merge_file_selections(request.files, request.mqtt_files)
        else:
            files = request.files

        if not files:
            raise ValueError("Select at least one file.")

        configs, all_tags, enabled_tags, skipped_files = self._build_configs_for_files(request, files, request.protocol)
        if not configs or enabled_tags == 0:
            raise ValueError(f"No {request.protocol.upper()} tags are enabled. Select at least one tag before applying the plan.")
        combined = configs[0].model_copy(deep=True)
        combined.tags = all_tags
        await self._wait_protocol(self.adapter.configure_tags(combined), f"{request.protocol.upper()} configuration")
        self.engines = [SimulatorEngine(self.adapter) for _ in configs]
        for engine, cfg in zip(self.engines, configs):
            await engine.configure(cfg, configure_adapter=False)
        self.configs = configs
        self.job_ids = [None] * len(self.engines)
        self.protocol = request.protocol
        self.assignment_mode = "shared"
        self.state = "configured"
        self.last_error = None
        return {
            "status": "configured",
            "protocol": request.protocol,
            "assignment_mode": "shared",
            "file_count": len(configs),
            "tag_count": enabled_tags,
            "skipped_files": skipped_files,
            "endpoint": self.adapter.get_endpoint(),
        }

    async def configure(self, config: ReplayConfig) -> dict[str, Any]:
        await self.stop()
        await self._wait_protocol(self.adapter.configure_tags(config), f"{config.protocol.upper()} configuration")
        engine = SimulatorEngine(self.adapter)
        await engine.configure(config, configure_adapter=False)
        self.engines = [engine]
        self.configs = [config]
        self.job_ids = [None]
        self.protocol = config.protocol
        self.assignment_mode = "shared"
        self.state = "configured"
        self.last_error = None
        return {"status": "configured", "protocol": config.protocol, "file_count": 1, "tag_count": len([t for t in config.tags if t.enabled]), "endpoint": self.adapter.get_endpoint()}

    def _configs_for_protocol(self, protocol: str) -> list[ReplayConfig]:
        return [cfg for cfg in self.configs if cfg.protocol == protocol or cfg.protocol == "both"]

    def _combined_config(self, protocol: str, configs: list[ReplayConfig]) -> ReplayConfig:
        combined = configs[-1].model_copy(deep=True)
        combined.protocol = protocol  # type: ignore[assignment]
        combined.tags = [tag.model_copy(deep=True) for cfg in configs for tag in cfg.tags if tag.enabled]
        return combined

    async def _reconfigure_managed_protocols(self) -> None:
        opc_configs = self._configs_for_protocol("opcua")
        mqtt_configs = self._configs_for_protocol("mqtt")

        if opc_configs:
            await self._wait_protocol(self.adapter.configure_channel_tags("opcua", self._combined_config("opcua", opc_configs)), "OPC UA managed configuration")
        else:
            await self.adapter.stop_channels("opcua")

        if mqtt_configs:
            await self._wait_protocol(self.adapter.configure_channel_tags("mqtt", self._combined_config("mqtt", mqtt_configs)), "MQTT managed configuration")
        else:
            await self.adapter.stop_channels("mqtt")

        if opc_configs and mqtt_configs:
            self.protocol = "both"
        elif opc_configs:
            self.protocol = "opcua"
        elif mqtt_configs:
            self.protocol = "mqtt"
        else:
            self.protocol = None
            self.state = "idle"

    async def add_job_config(self, job_id: str, config: ReplayConfig) -> dict[str, Any]:
        publisher = ReplayJobProtocolAdapter(self.adapter, config.protocol)
        engine = SimulatorEngine(publisher)
        await engine.configure(config, configure_adapter=False)
        with self._runtime_lock:
            self.engines.append(engine)
            self.configs.append(config)
            self.job_ids.append(job_id)
            try:
                await self._reconfigure_managed_protocols()
            except Exception:
                self.engines.pop()
                self.configs.pop()
                self.job_ids.pop()
                raise
            self.assignment_mode = "managed_jobs"
            self.state = "configured"
            self.last_error = None
            return self.get_job_status(job_id)

    async def start_job(self, job_id: str) -> dict[str, str]:
        engine = self._engine_for_job(job_id)
        await engine.publisher.start()
        result = await engine.start()
        self.state = "running"
        self.last_error = None
        return result

    async def stop_job(self, job_id: str, remove: bool = False) -> dict[str, str]:
        with self._runtime_lock:
            idx = self._job_index(job_id)
            engine = self.engines[idx]
        result = await engine.stop()
        if remove:
            await self.remove_job(job_id)
        elif all(e.state in ("stopped", "completed", "idle") for e in self.engines):
            self.state = "stopped"
        return result

    async def remove_job(self, job_id: str) -> None:
        with self._runtime_lock:
            idx = self._job_index(job_id)
            engine = self.engines.pop(idx)
            self.configs.pop(idx)
            self.job_ids.pop(idx)
        await engine.stop()
        with self._runtime_lock:
            await self._reconfigure_managed_protocols()
            if self.engines and any(e.state == "running" for e in self.engines):
                self.state = "running"
            elif not self.engines:
                self.state = "stopped"

    def _job_index(self, job_id: str) -> int:
        for idx, candidate in enumerate(self.job_ids):
            if candidate == job_id:
                return idx
        raise KeyError(f"Replay job is not active in the simulator: {job_id}")

    def _engine_for_job(self, job_id: str) -> SimulatorEngine:
        return self.engines[self._job_index(job_id)]

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        idx = self._job_index(job_id)
        status = self.engines[idx].get_status().model_dump()
        status["job_id"] = job_id
        return {
            "state": status.get("state"),
            "protocol": status.get("protocol"),
            "assignment_mode": "managed_jobs",
            "configured": status.get("configured"),
            "file_count": 1 if status.get("configured") else 0,
            "tag_count": status.get("tag_count") or 0,
            "row_count": status.get("row_count") or 0,
            "emitted_count": status.get("emitted_count") or 0,
            "cursor": status.get("cursor") or 0,
            "last_error": status.get("last_error"),
            "files": [status],
        }

    def _engines_for_protocol(self, protocol: str):
        selected = []
        for engine, cfg in zip(self.engines, self.configs):
            if protocol == "both" or cfg.protocol == protocol:
                selected.append(engine)
        return selected

    async def start(self) -> dict[str, str]:
        if not self.engines:
            raise ValueError("Configure at least one file first.")
        try:
            await self._wait_protocol(self.adapter.start(), "Protocol start")
            await asyncio.gather(*(engine.start() for engine in self.engines))
            self.state = "running"
            self.last_error = None
            return {"status": "running"}
        except Exception as exc:
            self.state = "error"
            self.last_error = self._start_error_message(exc, "Protocol start")
            raise RuntimeError(self.last_error) from exc

    async def start_protocol(self, protocol: str) -> dict[str, str]:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        selected = self._engines_for_protocol(protocol)
        if not selected:
            raise ValueError(f"No configured {protocol.upper()} replay plan. Apply the plan first.")
        try:
            if protocol in ("opcua", "both"):
                await self._wait_protocol(self.adapter.opcua.start(), "OPC UA start")
            if protocol in ("mqtt", "both"):
                await self._wait_protocol(self.adapter.mqtt.start(), "MQTT start")
            await asyncio.gather(*(engine.start() for engine in selected))
            self.state = "running"
            self.last_error = None
            return {"status": "running", "protocol": protocol}
        except Exception as exc:
            self.state = "error"
            self.last_error = self._start_error_message(exc, f"{protocol.upper()} start")
            raise RuntimeError(self.last_error) from exc

    async def stop(self) -> dict[str, str]:
        await asyncio.gather(*(engine.stop() for engine in self.engines), return_exceptions=True)
        await self.adapter.stop()
        self.state = "stopped"
        return {"status": "stopped"}

    async def stop_protocol(self, protocol: str) -> dict[str, str]:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        selected = self._engines_for_protocol(protocol)
        await asyncio.gather(*(engine.stop() for engine in selected), return_exceptions=True)
        if protocol in ("opcua", "both"):
            await self.adapter.opcua.stop()
        if protocol in ("mqtt", "both"):
            await self.adapter.mqtt.stop()
        if all((e.state in ("stopped", "completed", "idle") for e in self.engines)):
            self.state = "stopped"
        return {"status": "stopped", "protocol": protocol}

    async def restart(self) -> dict[str, str]:
        await asyncio.gather(*(engine.restart() for engine in self.engines))
        self.state = "running"
        return {"status": "running"}

    async def reset_cursor(self) -> dict[str, str]:
        await asyncio.gather(*(engine.reset_cursor() for engine in self.engines))
        return {"status": "cursor_reset"}

    def get_status(self) -> dict[str, Any]:
        statuses = [e.get_status().model_dump() for e in self.engines]
        for status, job_id in zip(statuses, self.job_ids):
            if job_id:
                status["job_id"] = job_id
        if statuses and self.state == "running":
            if any(s.get("state") == "error" for s in statuses):
                self.state = "error"
                self.last_error = next((s.get("last_error") for s in statuses if s.get("last_error")), self.last_error)
            elif all(s.get("state") == "completed" for s in statuses):
                self.state = "completed"
        tag_count = sum(s.get("tag_count") or 0 for s in statuses)
        row_count = sum(s.get("row_count") or 0 for s in statuses)
        emitted_count = sum(s.get("emitted_count") or 0 for s in statuses)
        opc_files = [c.csv_file for c in self.configs if c.protocol == "opcua"]
        mqtt_files = [c.csv_file for c in self.configs if c.protocol == "mqtt"]
        return {
            "state": self.state,
            "protocol": self.protocol,
            "assignment_mode": self.assignment_mode,
            "configured": bool(self.engines),
            "file_count": len(self.engines),
            "opcua_file_count": len(opc_files),
            "mqtt_file_count": len(mqtt_files),
            "csv_file": ", ".join(c.csv_file for c in self.configs) if self.configs else None,
            "opcua_files": opc_files,
            "mqtt_files": mqtt_files,
            "frequency_hz": self.configs[0].frequency_hz if self.configs else None,
            "cursor": min((s.get("cursor") or 0 for s in statuses), default=0),
            "row_count": row_count,
            "emitted_count": emitted_count,
            "tag_count": tag_count,
            "last_error": self.last_error,
            "files": statuses,
        }

    def get_current_values(self) -> CurrentValuesResponse:
        values = []
        updated_at = None
        for engine in self.engines:
            current = engine.get_current_values()
            values.extend(current.values)
            updated_at = current.updated_at or updated_at
        return CurrentValuesResponse(updated_at=updated_at or utc_now_iso(), values=values)
