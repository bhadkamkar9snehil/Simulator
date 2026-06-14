from __future__ import annotations

import datetime as dt
import inspect
import ipaddress
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any

from app.models import ReplayConfig

try:
    from asyncua import Server, ua  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without asyncua
    Server = None
    ua = None

log = logging.getLogger(__name__)


def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class OpcUaTagServer:
    """Single-root OPC UA server for all selected files.

    The server exposes exactly one root folder under Objects, normally:
        Objects / TagSimulator

    Multiple Excel/CSV files are represented below that same root by using
    unique variable names/node ids. This avoids creating a new TagSimulator
    folder every time another file is configured.
    """

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

    async def start(self) -> None:
        if self.running:
            return
        if Server is None:
            self.running = True
            self.mock_mode = True
            return
        self.server = Server()
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("Industrial Dual Protocol Tag Simulator")
        if hasattr(self.server, "set_application_uri"):
            self.server.set_application_uri(self.application_uri)

        # UaExpert expects the server to return an application instance
        # certificate during CreateSession, even when the selected endpoint is
        # SecurityPolicy=None / MessageSecurityMode=None.  Earlier builds did
        # not load a certificate, which caused: "Server did not return the
        # certificate used to create the secure channel."  We therefore create
        # and load a local self-signed server certificate, while still exposing
        # only the NoSecurity endpoint for simple simulator use.
        await self._configure_uaexpert_friendly_no_security()

        self.idx = await self.server.register_namespace(self.namespace_uri)
        await self.server.start()
        self.running = True

    async def stop(self) -> None:
        if self.server is not None and self.running:
            await self.server.stop()
        self.running = False
        self.variables.clear()
        self.server = None
        self.root_folder = None
        self.idx = None

    async def configure_tags(self, config: ReplayConfig) -> None:
        self.namespace_uri = config.namespace_uri
        self.variables.clear()

        if self.mock_mode or self.server is None:
            for tag in config.tags:
                if tag.enabled:
                    self.variables[tag.node_id] = {"value": tag.initial_value, "tag": tag}
            return

        self.idx = await self.server.register_namespace(config.namespace_uri)

        # One common root for all files. Do not create one root per Excel/CSV.
        self.root_folder = await self.server.nodes.objects.add_folder(self.idx, config.root_folder)

        used_names: set[str] = set()
        for tag in config.tags:
            if not tag.enabled:
                continue
            browse_name = self._browse_name(tag.node_id, tag.tag_name, used_names)
            value = self._initial_value(tag.data_type, tag.initial_value)
            var = await self.root_folder.add_variable(self.idx, browse_name, value)
            if tag.writable:
                await var.set_writable()
            self.variables[tag.node_id] = var

    async def update_values(self, values: dict[str, tuple[Any, str]]) -> None:
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

    def _browse_name(self, node_id: str, tag_name: str, used_names: set[str]) -> str:
        # Keep all file tags under one root and make every variable unique.
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
