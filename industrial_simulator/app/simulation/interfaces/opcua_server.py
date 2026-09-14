from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import ReplayConfig, TagMapping
from app.opcua_server import OpcUaTagServer, Server, ua
from app.opcua_support import (
    FixtureUserManager,
    identity_tokens,
    normalize_server_options,
    public_server_options,
    security_policy_types,
)

from ..models import SignalDefinition


class UnifiedOpcUaServer(OpcUaTagServer):
    """Security/auth specialization of the shared OPC UA host primitive.

    Datatype conversion, node creation, diagnostics, update semantics and server-loop
    ownership remain in ``OpcUaTagServer``. The unified runtime adds only server
    security/auth configuration plus adapters from ``SignalDefinition``.
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

        self.server = Server(user_manager=FixtureUserManager(self.server_options))
        await self.server.init()
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
        self._diagnostics_attached = self.diagnostics.attach(self.server)
        await self.server.start()
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

    @staticmethod
    def _tag_from_signal(
        signal: SignalDefinition,
        node_map: dict[str, str],
        data_types: dict[str, str],
        writable_signals: set[str],
    ) -> TagMapping:
        kwargs: dict[str, Any] = {
            "enabled": True,
            "csv_column": signal.name,
            "tag_name": signal.name,
            "node_id": node_map[signal.name],
            "data_type": data_types[signal.name],
            "writable": signal.name in writable_signals,
        }
        if "initial_value" in signal.model_fields_set:
            kwargs["initial_value"] = signal.initial_value
        return TagMapping(**kwargs)

    async def configure_signals(
        self,
        namespace_uri: str,
        root_folder: str,
        schema: list[SignalDefinition],
        node_map: dict[str, str],
        data_types: dict[str, str],
        writable_signals: set[str],
    ) -> None:
        """Adapt unified signal definitions into the canonical tag configuration path."""
        tags = [self._tag_from_signal(signal, node_map, data_types, writable_signals) for signal in schema]
        config = ReplayConfig(
            protocol="opcua",
            namespace_uri=namespace_uri,
            root_folder=root_folder,
            tags=tags,
        )
        await self.configure_tags(config)

    async def update_signals(
        self,
        values: dict[str, tuple[Any, str, str | int | None, str | None]],
    ) -> None:
        """Use the canonical host update path; no unified-runtime conversion fork."""
        await self.update_values(values)

    def get_status(self) -> dict[str, Any]:
        base = super().get_status()
        configured = public_server_options(self.server_options)
        configured["certificate_path"] = configured["certificate_path"] or base.get("certificate_path")
        return {**base, **configured}
