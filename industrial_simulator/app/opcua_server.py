from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import ipaddress
import logging
import os
import socket
import sys
import threading
import typing
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from app.models import ReplayConfig
from app.opcua_diagnostics import OpcUaDiagnostics
from app.opcua_types import coerce_value, data_value, default_value, variant_type

try:
    from asyncua import Server, ua  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without asyncua
    Server = None
    ua = None

log = logging.getLogger(__name__)
_ASYNCUA_314_HINTS_READY = False


def _prepare_asyncua_python314_type_hints() -> None:
    """Normalize asyncua 1.1.x generated annotations once on Python 3.14."""
    global _ASYNCUA_314_HINTS_READY
    if _ASYNCUA_314_HINTS_READY or ua is None or sys.version_info < (3, 14):
        return
    changed = False
    for candidate in vars(ua).values():
        if not isinstance(candidate, type) or not is_dataclass(candidate):
            continue
        module = sys.modules.get(candidate.__module__)
        annotations = getattr(candidate, "__annotations__", None)
        if module is None or not isinstance(annotations, dict):
            continue
        localns = {name: value for name, value in vars(candidate).items() if not isinstance(value, property)}
        try:
            hints = typing.get_type_hints(candidate, vars(module), localns)
        except Exception:
            continue
        for field_info in fields(candidate):
            resolved = hints.get(field_info.name)
            if resolved is None:
                continue
            if annotations.get(field_info.name) is not resolved:
                annotations[field_info.name] = resolved
                changed = True
            field_info.type = resolved
    if changed:
        from asyncua.ua import ua_binary  # type: ignore
        for name in ("create_dataclass_serializer", "create_type_serializer", "_create_dataclass_deserializer", "_create_type_deserializer"):
            cache_clear = getattr(getattr(ua_binary, name, None), "cache_clear", None)
            if cache_clear:
                cache_clear()
    _ASYNCUA_314_HINTS_READY = True


def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class OpcUaTagServer:
    """OPC UA replay server with explicit datatype fidelity and lightweight diagnostics."""

    def __init__(self, endpoint: str | None = None, advertised_endpoint: str | None = None):
        raw_port = str(os.environ.get("OPCUA_PORT", "4840")).strip()
        try:
            port = int(raw_port or "4840")
        except ValueError:
            port = 4840
        self.endpoint = endpoint or f"opc.tcp://0.0.0.0:{port}/simulator"
        self.advertised_endpoint = advertised_endpoint or f"opc.tcp://localhost:{port}/simulator"
        self.namespace_uri = "http://local/industrial-tag-simulator"
        self.application_uri = "urn:localhost:industrial-dual-protocol-tag-simulator"
        self.server: Any = None
        self.idx: int | None = None
        self.root_folder: Any = None
        self.variables: dict[str, Any] = {}
        self.tag_specs: dict[str, Any] = {}
        self.running = False
        self.mock_mode = Server is None
        self.security_policy = "None"
        self.certificate_path: str | None = None
        self.diagnostics = OpcUaDiagnostics()
        self._diagnostics_attached = False
        self._loop: Any = None
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()

    async def start(self) -> None:
        if self.running:
            return
        _prepare_asyncua_python314_type_hints()
        self.diagnostics.reset()
        if Server is None:
            self.running = True
            self.mock_mode = True
            return
        await self._run_in_server_loop(self._start_impl())

    async def _start_impl(self) -> None:
        if self.running:
            return
        self.server = Server()
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("Industrial Dual Protocol Tag Simulator")
        if hasattr(self.server, "set_application_uri"):
            await self._maybe_await(self.server.set_application_uri(self.application_uri))
        await self._configure_uaexpert_friendly_no_security()
        self.idx = await self.server.register_namespace(self.namespace_uri)
        self._diagnostics_attached = self.diagnostics.attach(self.server)
        await self.server.start()
        self.running = True

    async def stop(self) -> None:
        if not self.mock_mode and self._loop is not None:
            await self._run_in_server_loop(self._stop_impl())
            self._stop_server_loop()
            return
        await self._stop_impl()

    async def _stop_impl(self) -> None:
        if self.server is not None and self.running:
            await self.server.stop()
        self.running = False
        self.variables.clear()
        self.tag_specs.clear()
        self.server = None
        self.root_folder = None
        self.idx = None
        self._diagnostics_attached = False

    async def configure_tags(self, config: ReplayConfig) -> None:
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(self._configure_tags_impl(config))
            return
        await self._configure_tags_impl(config)

    @staticmethod
    def _initial_value_for_tag(tag: Any) -> Any:
        fields_set = getattr(tag, "model_fields_set", set())
        if "initial_value" in fields_set:
            return tag.initial_value
        return default_value(tag.data_type)

    async def _configure_tags_impl(self, config: ReplayConfig) -> None:
        self.namespace_uri = config.namespace_uri
        self.variables.clear()
        self.tag_specs.clear()
        enabled_tags = [tag for tag in config.tags if tag.enabled]
        node_ids = [str(tag.node_id).strip() for tag in enabled_tags]
        if any(not node_id for node_id in node_ids):
            raise ValueError("Every enabled OPC UA tag requires a non-empty NodeId.")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Enabled OPC UA tags must use unique NodeIds.")

        for tag in enabled_tags:
            self.tag_specs[tag.node_id] = tag

        if self.mock_mode or self.server is None:
            for tag in enabled_tags:
                initial = self._initial_value_for_tag(tag)
                self.variables[tag.node_id] = {
                    "value": coerce_value(tag.data_type, initial),
                    "data_type": tag.data_type,
                    "quality": tag.quality,
                    "source_timestamp": tag.source_timestamp,
                    "tag": tag,
                }
            return

        self.idx = await self.server.register_namespace(config.namespace_uri)
        self.root_folder = await self.server.nodes.objects.add_folder(self.idx, config.root_folder)
        used_names: set[str] = set()
        for tag in enabled_tags:
            browse_name = self._browse_name(tag.node_id, tag.tag_name, used_names)
            initial = self._initial_value_for_tag(tag)
            coerced = coerce_value(tag.data_type, initial)
            if ua is None:
                raise RuntimeError("asyncua UA types are unavailable.")
            var = await self.root_folder.add_variable(
                ua.NodeId(str(tag.node_id).strip(), self.idx),
                browse_name,
                ua.Variant(coerced, variant_type(tag.data_type)),
            )
            await var.write_attribute(
                ua.AttributeIds.Value,
                data_value(tag.data_type, initial, tag.quality, tag.source_timestamp),
            )
            if tag.writable:
                await var.set_writable()
            self.variables[tag.node_id] = var

    async def update_values(self, values: dict[str, Any]) -> None:
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(self._update_values_impl(values))
            return
        await self._update_values_impl(values)

    @staticmethod
    def _normalize_update(payload: Any, tag: Any) -> tuple[Any, str, Any, Any]:
        if isinstance(payload, dict):
            return (
                payload.get("value"),
                str(payload.get("data_type") or tag.data_type),
                payload.get("quality", tag.quality),
                payload.get("source_timestamp", tag.source_timestamp),
            )
        if not isinstance(payload, (list, tuple)):
            return payload, tag.data_type, tag.quality, tag.source_timestamp
        value = payload[0] if len(payload) > 0 else None
        data_type = str(payload[1]) if len(payload) > 1 and payload[1] else tag.data_type
        quality = payload[2] if len(payload) > 2 else tag.quality
        source_timestamp = payload[3] if len(payload) > 3 else tag.source_timestamp
        return value, data_type, quality, source_timestamp

    async def _update_values_impl(self, values: dict[str, Any]) -> None:
        for node_id, payload in values.items():
            var = self.variables.get(node_id)
            tag = self.tag_specs.get(node_id)
            if var is None or tag is None:
                continue
            value, data_type, quality, source_timestamp = self._normalize_update(payload, tag)
            if data_type != tag.data_type:
                raise ValueError(f"Datatype change for {node_id} is not allowed: configured {tag.data_type}, got {data_type}.")
            coerced = coerce_value(data_type, value)
            if self.mock_mode:
                var["value"] = coerced
                var["quality"] = quality
                var["source_timestamp"] = source_timestamp
            else:
                if ua is None:
                    raise RuntimeError("asyncua UA types are unavailable.")
                await var.write_attribute(
                    ua.AttributeIds.Value,
                    data_value(data_type, value, quality, source_timestamp),
                )

    def get_endpoint(self) -> str:
        return self.advertised_endpoint

    def get_status(self) -> dict[str, Any]:
        diagnostics = self.diagnostics.snapshot(self.server)
        return {
            "running": self.running,
            "endpoint": self.advertised_endpoint,
            "namespace_uri": self.namespace_uri,
            "mock_mode": self.mock_mode,
            "security_policy": self.security_policy,
            "certificate_path": self.certificate_path,
            "server_loop_running": bool(self._loop is not None and self._loop.is_running()),
            "server_thread_alive": bool(self._thread is not None and self._thread.is_alive()),
            "python314_asyncua_compat": _ASYNCUA_314_HINTS_READY,
            "diagnostics_available": self.mock_mode or self._diagnostics_attached,
            "diagnostics": diagnostics,
        }

    async def _configure_uaexpert_friendly_no_security(self) -> None:
        if self.server is None:
            return
        cert_file, key_file = self._certificate_files()
        self._ensure_certificate_files(cert_file, key_file)
        self.certificate_path = str(cert_file)
        await self._maybe_await(self.server.load_certificate(str(cert_file)))
        await self._maybe_await(self.server.load_private_key(str(key_file)))
        if ua is not None and hasattr(self.server, "set_security_policy"):
            self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            self.security_policy = "None"

    def _certificate_files(self) -> tuple[Path, Path]:
        cert_dir = get_base_dir() / "configs" / "opcua_certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        return cert_dir / "server_certificate.der", cert_dir / "server_private_key.pem"

    def _ensure_certificate_files(self, cert_file: Path, key_file: Path) -> None:
        if cert_file.exists() and key_file.exists():
            return
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("cryptography is required to generate the OPC UA server certificate. Run: python -m pip install -r requirements.txt") from exc
        hostname = socket.gethostname() or "localhost"
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Simulator"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Industrial Dual Protocol Tag Simulator"),
        ])
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = dt.datetime.now(dt.timezone.utc)
        alt_names: list[x509.GeneralName] = [
            x509.UniformResourceIdentifier(self.application_uri), x509.DNSName("localhost"), x509.DNSName(hostname),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.IPAddress(ipaddress.ip_address("::1")),
        ]
        cert = (
            x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(private_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=True, data_encipherment=True, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(private_key, hashes.SHA256())
        )
        key_file.write_bytes(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()))
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.DER))
        log.info("Generated OPC UA server certificate at %s", cert_file)

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _ensure_server_loop(self) -> None:
        with self._thread_lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return
            loop = asyncio.new_event_loop()
            def run_loop() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()
            self._loop = loop
            self._thread = threading.Thread(target=run_loop, name="OpcUaTagServerLoop", daemon=True)
            self._thread.start()

    async def _run_in_server_loop(self, coro: Any) -> Any:
        self._ensure_server_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(future)

    def _stop_server_loop(self) -> None:
        with self._thread_lock:
            loop = self._loop
            thread = self._thread
            self._loop = None
            self._thread = None
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)
        if loop is not None and not loop.is_closed():
            loop.close()

    @staticmethod
    def _browse_name(node_id: str, tag_name: str, used_names: set[str]) -> str:
        name = (node_id or tag_name).replace(".", "_").replace(" ", "_") or "Tag"
        base = name
        counter = 2
        while name in used_names:
            name = f"{base}_{counter}"
            counter += 1
        used_names.add(name)
        return name
