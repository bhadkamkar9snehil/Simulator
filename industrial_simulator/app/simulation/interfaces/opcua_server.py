from __future__ import annotations

from pathlib import Path
from typing import Any

from app.opcua_server import (
    OpcUaTagServer,
    Server,
    _patch_asyncua_python314_property_annotations,
    ua,
)
from app.opcua_support import (
    FixtureUserManager,
    coerce_value,
    identity_tokens,
    initial_value,
    normalize_server_options,
    opcua_timestamp,
    public_server_options,
    security_policy_types,
    status_code,
    variant_type,
)
from app.models import ReplayConfig

from ..models import SignalDefinition, utc_now_iso


class UnifiedOpcUaServer(OpcUaTagServer):
    """Unified-runtime OPC UA server with explicit security and scalar types.

    The legacy server remains intact while old replay callers are migrated. This
    subclass is intentionally small and reuses its event-loop/certificate code.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        advertised_endpoint: str | None = None,
        server_options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(endpoint, advertised_endpoint)
        self.server_options = normalize_server_options(server_options)
        self.application_uri = self.server_options["application_uri"]
        self.security_policy = self.server_options["security_policy"]
        self.authentication = self.server_options["authentication"]

    async def _start_impl(self) -> None:
        if self.running:
            return
        if Server is None or ua is None:
            raise RuntimeError("asyncua is required for OPC UA simulation.")

        _patch_asyncua_python314_property_annotations()
        self.server = Server(user_manager=FixtureUserManager(self.server_options))
        await self.server.init()
        _patch_asyncua_python314_property_annotations()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name(self.server_options["server_name"])
        if hasattr(self.server, "set_application_uri"):
            await self._maybe_await(self.server.set_application_uri(self.application_uri))

        cert_file, key_file = self._security_files()
        self.certificate_path = str(cert_file)
        await self._maybe_await(self.server.load_certificate(str(cert_file)))
        await self._maybe_await(self.server.load_private_key(str(key_file)))
        self.server.set_security_policy(security_policy_types(self.security_policy))
        tokens = identity_tokens(self.authentication)
        if hasattr(self.server, "set_identity_tokens"):
            self.server.set_identity_tokens(tokens)
        else:  # asyncua 1.1 compatibility
            policy_ids: list[str] = []
            if ua.AnonymousIdentityToken in tokens:
                policy_ids.append("Anonymous")
            if ua.UserNameIdentityToken in tokens:
                policy_ids.append("Username")
            self.server.set_security_IDs(policy_ids)

        self.idx = await self.server.register_namespace(self.namespace_uri)
        await self.server.start()
        _patch_asyncua_python314_property_annotations()
        self.running = True

    def _security_files(self) -> tuple[Path, Path]:
        cert_override = self.server_options["certificate_path"]
        key_override = self.server_options["private_key_path"]
        if bool(cert_override) != bool(key_override):
            raise ValueError("OPC UA certificate_path and private_key_path must be supplied together.")
        if cert_override and key_override:
            cert_file = Path(cert_override).expanduser().resolve()
            key_file = Path(key_override).expanduser().resolve()
            if not cert_file.is_file():
                raise ValueError(f"OPC UA certificate file not found: {cert_file}")
            if not key_file.is_file():
                raise ValueError(f"OPC UA private key file not found: {key_file}")
            return cert_file, key_file
        cert_file, key_file = self._certificate_files()
        self._ensure_certificate_files(cert_file, key_file)
        return cert_file, key_file

    async def configure_signals(
        self,
        namespace_uri: str,
        root_folder: str,
        schema: list[SignalDefinition],
        node_map: dict[str, str],
        data_types: dict[str, str],
        writable_signals: set[str],
    ) -> None:
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(
                self._configure_signals_impl(
                    namespace_uri,
                    root_folder,
                    schema,
                    node_map,
                    data_types,
                    writable_signals,
                )
            )
            return
        await self._configure_signals_impl(
            namespace_uri,
            root_folder,
            schema,
            node_map,
            data_types,
            writable_signals,
        )

    async def _configure_signals_impl(
        self,
        namespace_uri: str,
        root_folder: str,
        schema: list[SignalDefinition],
        node_map: dict[str, str],
        data_types: dict[str, str],
        writable_signals: set[str],
    ) -> None:
        self.namespace_uri = namespace_uri
        self.variables.clear()
        node_ids = [str(node_map[signal.name]).strip() for signal in schema]
        if any(not node_id for node_id in node_ids):
            raise ValueError("Every enabled OPC UA tag requires a non-empty NodeId.")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Enabled OPC UA tags must use unique NodeIds.")

        if self.mock_mode or self.server is None:
            for signal in schema:
                data_type = data_types[signal.name]
                self.variables[node_map[signal.name]] = {
                    "value": initial_value(data_type, signal.initial_value),
                    "signal": signal,
                    "data_type": data_type,
                    "writable": signal.name in writable_signals,
                    "quality": "GOOD",
                    "source_timestamp": None,
                }
            return

        self.idx = await self.server.register_namespace(namespace_uri)
        self.root_folder = await self.server.nodes.objects.add_folder(self.idx, root_folder)
        used_names: set[str] = set()
        for signal in schema:
            node_id = node_map[signal.name]
            data_type = data_types[signal.name]
            browse_name = self._browse_name(node_id, signal.name, used_names)
            value = initial_value(data_type, signal.initial_value)
            var = await self.root_folder.add_variable(
                ua.NodeId(str(node_id).strip(), self.idx),
                browse_name,
                value,
                varianttype=variant_type(data_type),
            )
            if signal.name in writable_signals:
                await var.set_writable()
            self.variables[node_id] = var
        _patch_asyncua_python314_property_annotations()

    async def update_signals(
        self,
        values: dict[str, tuple[Any, str, str | None, str | None]],
    ) -> None:
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(self._update_signals_impl(values))
            return
        await self._update_signals_impl(values)

    async def _update_signals_impl(
        self,
        values: dict[str, tuple[Any, str, str | None, str | None]],
    ) -> None:
        for node_id, (value, data_type, quality, source_timestamp) in values.items():
            var = self.variables.get(node_id)
            if var is None:
                continue
            typed = coerce_value(value, data_type)
            timestamp = opcua_timestamp(source_timestamp)
            if self.mock_mode:
                var["value"] = typed
                var["data_type"] = data_type
                var["quality"] = quality or "GOOD"
                var["source_timestamp"] = timestamp
                continue
            data_value = ua.DataValue(
                ua.Variant(typed, variant_type(data_type)),
                StatusCode=status_code(quality),
                SourceTimestamp=timestamp,
                ServerTimestamp=opcua_timestamp(utc_now_iso()),
            )
            await var.write_value(data_value)

    async def _configure_tags_impl(self, config: ReplayConfig) -> None:
        data_types = {tag.tag_name: tag.data_type for tag in config.tags if tag.enabled}
        writable = {tag.tag_name for tag in config.tags if tag.enabled and tag.writable}
        schema = [
            SignalDefinition(
                name=tag.tag_name,
                node_id=tag.node_id,
                data_type=tag.data_type,
                initial_value=tag.initial_value,
                writable=tag.writable,
            )
            for tag in config.tags
            if tag.enabled
        ]
        node_map = {signal.name: signal.node_id for signal in schema}
        await self._configure_signals_impl(
            config.namespace_uri,
            config.root_folder,
            schema,
            node_map,
            data_types,
            writable,
        )

    async def _update_values_impl(self, values: dict[str, tuple[Any, str]]) -> None:
        converted = {
            node_id: (value, data_type, "GOOD", None)
            for node_id, (value, data_type) in values.items()
        }
        await self._update_signals_impl(converted)

    def get_status(self) -> dict[str, Any]:
        base = super().get_status()
        configured = public_server_options(self.server_options)
        configured["certificate_path"] = configured["certificate_path"] or base.get("certificate_path")
        return {**base, **configured}
