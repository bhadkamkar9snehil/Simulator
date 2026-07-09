import asyncio
import threading

import paho.mqtt.client as mqtt

from app.mqtt_broker import SimpleMqttBroker, _topic_matches


def _client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv311)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


def test_topic_filter_matching_supports_mqtt_wildcards():
    assert _topic_matches("plant/+/quality", "plant/urea/quality")
    assert _topic_matches("plant/#", "plant/urea/reactor/temperature")
    assert not _topic_matches("plant/+/quality", "plant/urea/reactor/quality")
    assert not _topic_matches("plant/#/quality", "plant/urea/quality")


def test_paho_clients_publish_and_subscribe_through_broker():
    async def run() -> tuple[list[tuple[str, bytes]], int, int]:
        broker = SimpleMqttBroker()
        server = await asyncio.start_server(broker.handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        messages: list[tuple[str, bytes]] = []
        subscriber_connected = threading.Event()
        publisher_connected = threading.Event()
        subscribed = threading.Event()
        received = threading.Event()
        subscriber = _client("pytest-subscriber")
        publisher = _client("pytest-publisher")

        def on_subscriber_connect(*_args):
            subscriber_connected.set()

        def on_publisher_connect(*_args):
            publisher_connected.set()

        def on_message(_client, _userdata, message):
            messages.append((message.topic, message.payload))
            received.set()

        def on_subscribe(*_args):
            subscribed.set()

        subscriber.on_connect = on_subscriber_connect
        subscriber.on_message = on_message
        subscriber.on_subscribe = on_subscribe
        publisher.on_connect = on_publisher_connect
        try:
            assert subscriber.connect("127.0.0.1", port, keepalive=30) == mqtt.MQTT_ERR_SUCCESS
            subscriber.loop_start()
            assert await asyncio.to_thread(subscriber_connected.wait, 3)
            result, _mid = subscriber.subscribe("plant/+/quality", qos=0)
            assert result == mqtt.MQTT_ERR_SUCCESS
            assert await asyncio.to_thread(subscribed.wait, 3)

            assert publisher.connect("127.0.0.1", port, keepalive=30) == mqtt.MQTT_ERR_SUCCESS
            publisher.loop_start()
            assert await asyncio.to_thread(publisher_connected.wait, 3)
            info = publisher.publish("plant/urea/quality", b'{"ok":true}', qos=1)
            await asyncio.to_thread(info.wait_for_publish, timeout=3)
            assert info.is_published()
            assert await asyncio.to_thread(received.wait, 3)
            return messages, broker.messages_received, broker.messages_delivered
        finally:
            publisher.disconnect()
            subscriber.disconnect()
            publisher.loop_stop()
            subscriber.loop_stop()
            server.close()
            await server.wait_closed()

    messages, received_count, delivered_count = asyncio.run(run())
    assert messages == [("plant/urea/quality", b'{"ok":true}')]
    assert received_count == 1
    assert delivered_count == 1
