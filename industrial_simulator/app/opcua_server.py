from __future__ import annotations

import datetime as dt
import asyncio
import functools
import inspect
import ipaddress
import logging
import os
import socket
import sys
import threading
from dataclasses import MISSING, Field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args

from app.models import ReplayConfig

try:
    from asyncua import Server, ua  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without asyncua
    Server = None
    ua = None

log = logging.getLogger(__name__)


def _patch_asyncua_python314_property_annotations() -> None:
    """Repair asyncua generated dataclass field types on Python 3.14.

    asyncua 1.1.x generates fields such as ``RequestHeader_: RequestHeader``
    and then defines a ``RequestHeader`` property on the same class. On Python
    3.14 those field types can resolve to the property object, which breaks
    binary serialization before an OPC UA client can open a secure channel.
    """
    if ua is None:
        return

    def infer_field_type(field_info: Any) -> type[Any] | None:
        factory = getattr(field_info, "default_factory", MISSING)
        if factory is not MISSING:
            try:
                return type(factory())
            except Exception:
                return None
        if field_info.default is not MISSING:
            return type(field_info.default)
        return None

    def repair_field_type(field_type: Any, dataclazz: type[Any]) -> Any:
        if isinstance(field_type, Field):
            replacement = infer_field_type(field_type)
            return replacement if replacement is not None else field_type

        if field_type is type(None):
            for candidate in fields(dataclazz):
                if candidate.type is not field_type:
                    continue
                generated_name = candidate.name[:-1] if candidate.name.endswith("_") else candidate.name
                alias = getattr(ua, generated_name, None)
                if isinstance(alias, type):
                    return alias
                replacement = infer_field_type(candidate)
                if replacement is not None and replacement is not type(None):
                    return replacement
            return field_type

        if isinstance(field_type, property):
            for candidate in fields(dataclazz):
                if candidate.type is field_type:
                    generated_name = candidate.name[:-1] if candidate.name.endswith("_") else candidate.name
                    alias = getattr(ua, generated_name, None)
                    if isinstance(alias, type):
                        return alias
                    replacement = infer_field_type(candidate)
                    if replacement is not None and replacement is not type(None):
                        return replacement
            property_name = getattr(getattr(field_type, "fget", None), "__name__", None)
            if property_name:
                alias = getattr(ua, property_name, None)
                if isinstance(alias, type):
                    return alias
                generated_field_name = f"{property_name}_"
                for candidate in fields(dataclazz):
                    if candidate.name == generated_field_name:
                        replacement = infer_field_type(candidate)
                        if replacement is not None and replacement is not type(None):
                            return replacement
            property_fields = [candidate for candidate in fields(dataclazz) if isinstance(candidate.type, property)]
            if len(property_fields) == 1:
                generated_name = property_fields[0].name[:-1] if property_fields[0].name.endswith("_") else property_fields[0].name
                alias = getattr(ua, generated_name, None)
                if isinstance(alias, type):
                    return alias
                replacement = infer_field_type(property_fields[0])
                if replacement is not None and replacement is not type(None):
                    return replacement
            return field_type

        args = get_args(field_type)
        if not args or not any(isinstance(arg, property) for arg in args):
            return field_type

        replacement: type[Any] | None = None
        for candidate in fields(dataclazz):
            if candidate.type is field_type:
                replacement = infer_field_type(candidate)
                break
        if replacement is None:
            for arg in args:
                if not isinstance(arg, property):
                    continue
                property_name = getattr(getattr(arg, "fget", None), "__name__", None)
                if not property_name:
                    continue
                generated_field_name = f"{property_name}_"
                for candidate in fields(dataclazz):
                    if candidate.name == generated_field_name:
                        replacement = infer_field_type(candidate)
                        break
                if replacement is not None:
                    break
        if replacement is None:
            property_fields = [candidate for candidate in fields(dataclazz) if get_args(candidate.type) and any(isinstance(arg, property) for arg in get_args(candidate.type))]
            if len(property_fields) == 1:
                replacement = infer_field_type(property_fields[0])
        if replacement is None:
            return field_type

        fixed_args = [replacement if isinstance(arg, property) else arg for arg in args]
        repaired = fixed_args[0]
        for arg in fixed_args[1:]:
            repaired = repaired | arg
        return repaired

    for candidate in vars(ua).values():
        if not isinstance(candidate, type) or not is_dataclass(candidate):
            continue
        for field_info in fields(candidate):
            repaired = repair_field_type(field_info.type, candidate)
            if repaired is not field_info.type:
                field_info.type = repaired
    try:
        from asyncua.ua import ua_binary  # type: ignore

        ua_binary.create_dataclass_serializer.cache_clear()
        ua_binary.create_type_serializer.cache_clear()
        ua_binary._create_dataclass_deserializer.cache_clear()
        ua_binary._create_type_deserializer.cache_clear()
        original_field_serializer = getattr(ua_binary, "_its_original_field_serializer", ua_binary.field_serializer)
        original_type_deserializer = getattr(ua_binary, "_its_original_type_deserializer", ua_binary._create_type_deserializer)

        if not hasattr(ua_binary, "_its_original_field_serializer"):
            ua_binary._its_original_field_serializer = original_field_serializer

            def field_serializer_compat(field_type: Any, dataclazz: type[Any]) -> Any:
                return original_field_serializer(repair_field_type(field_type, dataclazz), dataclazz)

            ua_binary.field_serializer = field_serializer_compat
        if not hasattr(ua_binary, "_its_original_type_deserializer"):
            ua_binary._its_original_type_deserializer = original_type_deserializer

            @functools.lru_cache(maxsize=None)
            def type_deserializer_compat(field_type: Any, dataclazz: type[Any]) -> Any:
                repaired = repair_field_type(field_type, dataclazz)
                try:
                    return original_type_deserializer(repaired, dataclazz)
                except TypeError:
                    log.exception("asyncua deserializer type repair failed for %r field type %r repaired to %r", dataclazz, field_type, repaired)
                    raise

            ua_binary._create_type_deserializer = type_deserializer_compat
    except Exception:
        pass


_patch_asyncua_python314_property_annotations()


def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class OpcUaTagServer:
    """Single-root OPC UA server for all configured tags."""

    def __init__(self, endpoint: str | None = None, advertised_endpoint: str | None = None):
        raw_port = str(os.environ.get("OPCUA_PORT", "4840")).strip()
        try:
            port = int(raw_port or "4840")
        except ValueError:
            port = 4840
        endpoint = endpoint or f"opc.tcp://0.0.0.0:{port}/simulator"
        advertised_endpoint = advertised_endpoint or f"opc.tcp://localhost:{port}/simulator"
        self.endpoint = endpoint
        self.advertised_endpoint = advertised_endpoint
        self.namespace_uri = "http://local/industrial-tag-simulator"
        self.application_uri = "urn:localhost:industrial-dual-protocol-tag-simulator"
        self.server: Any = None
        self.idx: int | None = None
        self.root_folder: Any = None
        self.variables: dict[str, Any] = {}
        self.running = False
        self.mock_mode = Server is None
        self.security_policy = "None"
        self.certificate_path: str | None = None
        self._loop: Any = None
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()

    async def start(self) -> None:
        if self.running:
            return
        _patch_asyncua_python314_property_annotations()
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
        _patch_asyncua_python314_property_annotations()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("Industrial Dual Protocol Tag Simulator")
        if hasattr(self.server, "set_application_uri"):
            await self._maybe_await(self.server.set_application_uri(self.application_uri))
        await self._configure_uaexpert_friendly_no_security()
        self.idx = await self.server.register_namespace(self.namespace_uri)
        await self.server.start()
        _patch_asyncua_python314_property_annotations()
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
        self.server = None
        self.root_folder = None
        self.idx = None

    async def configure_tags(self, config: ReplayConfig) -> None:
        _patch_asyncua_python314_property_annotations()
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(self._configure_tags_impl(config))
            return
        await self._configure_tags_impl(config)

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
                self.variables[tag.node_id] = {"value": tag.initial_value, "tag": tag}
            return

        self.idx = await self.server.register_namespace(config.namespace_uri)
        self.root_folder = await self.server.nodes.objects.add_folder(self.idx, config.root_folder)

        used_names: set[str] = set()
        for tag in enabled_tags:
            browse_name = self._browse_name(tag.node_id, tag.tag_name, used_names)
            value = self._initial_value(tag.data_type, tag.initial_value)
            if ua is None:  # pragma: no cover - real asyncua server implies ua exists
                raise RuntimeError("asyncua UA types are unavailable.")
            var = await self.root_folder.add_variable(
                ua.NodeId(str(tag.node_id).strip(), self.idx),
                browse_name,
                value,
            )
            if tag.writable:
                await var.set_writable()
            self.variables[tag.node_id] = var
        _patch_asyncua_python314_property_annotations()

    async def update_values(self, values: dict[str, tuple[Any, str]]) -> None:
        if not self.mock_mode and self.server is not None:
            await self._run_in_server_loop(self._update_values_impl(values))
            return
        await self._update_values_impl(values)

    async def _update_values_impl(self, values: dict[str, tuple[Any, str]]) -> None:
        for node_id, (value, data_type) in values.items():
            var = self.variables.get(node_id)
            if var is None:
                continue
            if self.mock_mode:
                var["value"] = value
            else:
                await var.write_value(value)

    def get_endpoint(self) -> str:
        return self.advertised_endpoint

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "endpoint": self.advertised_endpoint,
            "namespace_uri": self.namespace_uri,
            "mock_mode": self.mock_mode,
            "security_policy": self.security_policy,
            "certificate_path": self.certificate_path,
            "server_loop_running": bool(self._loop is not None and self._loop.is_running()),
            "server_thread_alive": bool(self._thread is not None and self._thread.is_alive()),
            "python314_asyncua_compat": True,
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
        except Exception as exc:  # pragma: no cover - dependency issue in runtime env
            raise RuntimeError(
                "cryptography is required to generate the OPC UA server certificate. "
                "Run: python -m pip install -r requirements.txt"
            ) from exc

        hostname = socket.gethostname() or "localhost"
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Simulator"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Industrial Dual Protocol Tag Simulator"),
        ])
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = dt.datetime.now(dt.timezone.utc)
        alt_names: list[x509.GeneralName] = [
            x509.UniformResourceIdentifier(self.application_uri),
            x509.DNSName("localhost"),
            x509.DNSName(hostname),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1")),
        ]
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=True,
                    data_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )
        key_file.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.DER))
        log.info("Generated OPC UA server certificate at %s", cert_file)

    async def _maybe_await(self, value: Any) -> Any:
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

    def _browse_name(self, node_id: str, tag_name: str, used_names: set[str]) -> str:
        name = (node_id or tag_name).replace(".", "_").replace(" ", "_")
        if not name:
            name = "Tag"
        base = name
        counter = 2
        while name in used_names:
            name = f"{base}_{counter}"
            counter += 1
        used_names.add(name)
        return name

    def _initial_value(self, data_type: str, value: Any) -> Any:
        if value is not None:
            return value
        if data_type == "Double":
            return 0.0
        if data_type == "Int64":
            return 0
        if data_type == "Boolean":
            return False
        return ""
