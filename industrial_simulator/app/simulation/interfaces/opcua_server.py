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
    public_server_options,
    security_policy_types,
    variant_type,
)
from app.models import ReplayConfig


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

    async def _configure_tags_impl(self, config: ReplayConfig) -> None:
        self.namespace_uri = config.namespace_uri
        self.variables.clear()
        enabled_tags = [tag for tag in config.tags if tag.enabled]
        node_ids = [str(tag.node_id).strip() for tag in enabled_tags]
        if any(not node_id for node_id in node_ids):
            raise ValueError("Every enabled OPC UA tag requires a non-empty NodeId.")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Enabled OPC UA tags must use unique NodeIds.")

        if self.mock_mode or self.server is None:
            for tag in enabled_tags:
                self.variables[tag.node_id] = {
                    "value": initial_value(tag.data_type, tag.initial_value),
                    "tag": tag,
                }
            return

        self.idx = await self.server.register_namespace(config.namespace_uri)
        self.root_folder = await self.server.nodes.objects.add_folder(self.idx, config.root_folder)
        used_names: set[str] = set()
        for tag in enabled_tags:
            browse_name = self._browse_name(tag.node_id, tag.tag_name, used_names)
            value = initial_value(tag.data_type, tag.initial_value)
            var = await self.root_folder.add_variable(
                ua.NodeId(str(tag.node_id).strip(), self.idx),
                browse_name,
                value,
                varianttype=variant_type(tag.data_type),
            )
            if tag.writable:
                await var.set_writable()
            self.variables[tag.node_id] = var
        _patch_asyncua_python314_property_annotations()

    async def _update_values_impl(self, values: dict[str, tuple[Any, str]]) -> None:
        for node_id, (value, data_type) in values.items():
            var = self.variables.get(node_id)
            if var is None:
                continue
            typed = coerce_value(value, data_type)
            if self.mock_mode:
                var["value"] = typed
            else:
                await var.write_value(typed, varianttype=variant_type(data_type))

    def get_status(self) -> dict[str, Any]:
        return {
            **super().get_status(),
            **public_server_options(self.server_options),
        }
