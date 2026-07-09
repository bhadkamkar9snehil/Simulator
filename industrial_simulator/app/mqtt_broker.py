from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("industrial.mqtt_broker")

MAX_PACKET_SIZE = 16 * 1024 * 1024


class MqttProtocolError(Exception):
    pass


def _encode_remaining_length(length: int) -> bytes:
    if length < 0:
        raise ValueError("length must be positive")
    encoded = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        encoded.append(byte)
        if length == 0:
            return bytes(encoded)


async def _read_remaining_length(reader: asyncio.StreamReader) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        raw = await reader.readexactly(1)
        byte = raw[0]
        value += (byte & 0x7F) * multiplier
        if (byte & 0x80) == 0:
            if value > MAX_PACKET_SIZE:
                raise MqttProtocolError("MQTT packet is too large.")
            return value
        multiplier *= 128
    raise MqttProtocolError("Malformed MQTT remaining length.")


async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(1)
    remaining = await _read_remaining_length(reader)
    payload = await reader.readexactly(remaining) if remaining else b""
    return header[0], payload


def _read_utf8(payload: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(payload):
        raise MqttProtocolError("Malformed MQTT string.")
    length = int.from_bytes(payload[offset : offset + 2], "big")
    offset += 2
    if offset + length > len(payload):
        raise MqttProtocolError("Malformed MQTT string length.")
    return payload[offset : offset + length].decode("utf-8", errors="replace"), offset + length


def _write_utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return len(raw).to_bytes(2, "big") + raw


def _topic_matches(topic_filter: str, topic: str) -> bool:
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")
    for idx, part in enumerate(filter_parts):
        if part == "#":
            return idx == len(filter_parts) - 1
        if idx >= len(topic_parts):
            return False
        if part != "+" and part != topic_parts[idx]:
            return False
    return len(topic_parts) == len(filter_parts)


def _publish_packet(topic: str, payload: bytes, retain: bool = False) -> bytes:
    variable = _write_utf8(topic) + payload
    flags = 0x01 if retain else 0x00
    return bytes([0x30 | flags]) + _encode_remaining_length(len(variable)) + variable


@dataclass(eq=False)
class BrokerClient:
    writer: asyncio.StreamWriter
    client_id: str = ""
    subscriptions: set[str] = field(default_factory=set)


class SimpleMqttBroker:
    def __init__(self) -> None:
        self.clients: set[BrokerClient] = set()
        self._lock = asyncio.Lock()
        self.messages_received = 0
        self.messages_delivered = 0

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = BrokerClient(writer=writer)
        peer = writer.get_extra_info("peername")
        try:
            while True:
                header, payload = await _read_packet(reader)
                packet_type = header >> 4
                flags = header & 0x0F
                if packet_type == 1:
                    await self._handle_connect(client, payload)
                    log.info("MQTT client connected: %s from %s", client.client_id, peer)
                elif packet_type == 3:
                    await self._handle_publish(client, flags, payload)
                elif packet_type == 8:
                    await self._handle_subscribe(client, payload)
                elif packet_type == 12:
                    writer.write(b"\xD0\x00")
                    await writer.drain()
                elif packet_type == 14:
                    break
                else:
                    raise MqttProtocolError(f"Unsupported MQTT packet type: {packet_type}")
        except asyncio.IncompleteReadError:
            pass
        except Exception:
            log.exception("MQTT client failed: %s", client.client_id or peer)
        finally:
            await self._remove_client(client)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_connect(self, client: BrokerClient, payload: bytes) -> None:
        protocol_name, offset = _read_utf8(payload, 0)
        if offset + 4 > len(payload):
            raise MqttProtocolError("Malformed MQTT CONNECT.")
        protocol_level = payload[offset]
        offset += 1
        connect_flags = payload[offset]
        offset += 1
        offset += 2  # keep alive
        supported = (protocol_name == "MQTT" and protocol_level == 4) or (protocol_name == "MQIsdp" and protocol_level == 3)
        if not supported:
            raise MqttProtocolError(f"Unsupported MQTT protocol {protocol_name} level {protocol_level}.")
        client_id, offset = _read_utf8(payload, offset)
        if not client_id:
            client_id = f"anonymous-{id(client):x}"
        client.client_id = client_id
        if connect_flags & 0x04:
            _will_topic, offset = _read_utf8(payload, offset)
            _will_message, offset = _read_utf8(payload, offset)
        if connect_flags & 0x80:
            _username, offset = _read_utf8(payload, offset)
        if connect_flags & 0x40:
            _password, offset = _read_utf8(payload, offset)
        async with self._lock:
            self.clients.add(client)
        client.writer.write(b"\x20\x02\x00\x00")
        await client.writer.drain()

    async def _handle_publish(self, client: BrokerClient, flags: int, payload: bytes) -> None:
        topic, offset = _read_utf8(payload, 0)
        qos = (flags >> 1) & 0x03
        if qos > 1:
            raise MqttProtocolError("MQTT QoS 2 is not supported by the simulator broker.")
        packet_id = b""
        if qos:
            if offset + 2 > len(payload):
                raise MqttProtocolError("Malformed MQTT packet id.")
            packet_id = payload[offset : offset + 2]
            offset += 2
        body = payload[offset:]
        self.messages_received += 1
        await self._deliver(topic, body, retain=bool(flags & 0x01))
        if qos == 1 and packet_id:
            # PUBACK back to the publisher. QoS 2 is intentionally not supported.
            client.writer.write(b"\x40\x02" + packet_id)
            await client.writer.drain()

    async def _handle_subscribe(self, client: BrokerClient, payload: bytes) -> None:
        if len(payload) < 3:
            raise MqttProtocolError("Malformed MQTT SUBSCRIBE.")
        packet_id = payload[:2]
        offset = 2
        accepted = bytearray()
        while offset < len(payload):
            topic_filter, offset = _read_utf8(payload, offset)
            if offset >= len(payload):
                raise MqttProtocolError("Malformed MQTT subscription options.")
            _options = payload[offset]
            offset += 1
            client.subscriptions.add(topic_filter)
            accepted.append(0)
        remaining = packet_id + bytes(accepted)
        client.writer.write(b"\x90" + _encode_remaining_length(len(remaining)) + remaining)
        await client.writer.drain()

    async def _deliver(self, topic: str, payload: bytes, retain: bool = False) -> None:
        async with self._lock:
            clients = list(self.clients)
        packet = _publish_packet(topic, payload, retain=retain)
        for client in clients:
            if not any(_topic_matches(topic_filter, topic) for topic_filter in client.subscriptions):
                continue
            try:
                client.writer.write(packet)
                await client.writer.drain()
                self.messages_delivered += 1
            except Exception:
                await self._remove_client(client)

    async def _remove_client(self, client: BrokerClient) -> None:
        async with self._lock:
            self.clients.discard(client)


async def serve(host: str = "0.0.0.0", port: int = 1883) -> None:
    broker = SimpleMqttBroker()
    server = await asyncio.start_server(broker.handle_client, host, port)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    log.info("Simulator MQTT broker listening on %s", addrs)
    async with server:
        await server.serve_forever()


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    raw_port = os.environ.get("MQTT_BROKER_PORT") or os.environ.get("MQTT_PORT") or "1883"
    try:
        port = int(raw_port)
    except ValueError:
        port = 1883
    asyncio.run(serve(port=port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
