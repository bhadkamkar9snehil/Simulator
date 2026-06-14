import pytest
from app.simulator import SimulatorEngine
from app.mqtt_publisher import MqttTagPublisher
from app.models import ReplayConfig, TagMapping


@pytest.mark.asyncio
async def test_simulator_loop_modes(tmp_path, monkeypatch):
    from app import csv_manager
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, 'generated', tmp_path)
    p = tmp_path / 'x.csv'
    p.write_text('timestamp,value\n2026-01-01T00:00:00Z,1\n2026-01-01T00:00:01Z,2\n', encoding='utf-8')
    publisher = MqttTagPublisher()
    publisher.mock_mode = True
    await publisher.start()
    sim = SimulatorEngine(publisher)
    cfg = ReplayConfig(csv_file='x.csv', csv_source='generated', frequency_hz=1, loop_mode='once', timestamp_mode='wall_clock', start_row=0, tags=[TagMapping(enabled=True, csv_column='value', tag_name='Value', node_id='TagSimulator.Value', data_type='Int64')])
    await sim.configure(cfg)
    await sim.emit_once()
    assert sim.get_current_values().values[0].value == 1
    sim._advance_cursor()
    await sim.emit_once()
    assert sim.get_current_values().values[0].value == 2


def test_mqtt_streampipes_payload_includes_csv_column_aliases():
    publisher = MqttTagPublisher()
    tag = TagMapping(
        enabled=True,
        csv_column='arc_stability_index',
        tag_name='eaf_melting_arc_stability_index',
        node_id='TagSimulator.eaf_melting.arc_stability_index',
        data_type='Double',
    )
    publisher.tags = {tag.node_id: tag}

    payload = publisher._build_flat_payload(
        {tag.node_id: (0.8295, 'Double')},
        timestamp='2026-05-15T07:21:05Z',
    )

    assert payload['published_at'] == '2026-05-15T07:21:05Z'
    assert payload['eaf_melting_arc_stability_index'] == 0.8295
    assert payload['arc_stability_index'] == 0.8295


def test_mqtt_streampipes_payload_renames_csv_timestamp_alias():
    publisher = MqttTagPublisher()
    tag = TagMapping(
        enabled=True,
        csv_column='timestamp',
        tag_name='eaf_melting_timestamp',
        node_id='TagSimulator.eaf_melting.timestamp',
        data_type='String',
    )
    publisher.tags = {tag.node_id: tag}

    payload = publisher._build_flat_payload(
        {tag.node_id: ('2026-01-01T00:00:00Z', 'String')},
        timestamp='2026-05-15T07:21:05Z',
    )

    assert payload['eaf_melting_timestamp'] == '2026-01-01T00:00:00Z'
    assert payload['csv_timestamp'] == '2026-01-01T00:00:00Z'
