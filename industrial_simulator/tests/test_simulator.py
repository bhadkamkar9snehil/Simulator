import asyncio
from app import dataset_manager
from app.simulator import SimulatorEngine
from app.mqtt_publisher import MqttTagPublisher
from app.models import DatasetManifest, DatasetSchemaField, ReplayConfig, TagMapping


def test_simulator_loop_modes(tmp_path, monkeypatch):
    async def run() -> None:
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
        assert sim.rows == []
        assert sim.row_count == 2
        await sim.emit_once()
        assert sim.get_current_values().values[0].value == 1
        sim._advance_cursor()
        await sim.emit_once()
        assert sim.get_current_values().values[0].value == 2

    asyncio.run(run())


def test_csv_timestamp_replay_preserves_naive_local_time(tmp_path, monkeypatch):
    async def run() -> None:
        from app import csv_manager
        monkeypatch.setitem(csv_manager.SOURCE_DIRS, 'generated', tmp_path)
        p = tmp_path / 'x.csv'
        p.write_text('timestamp,value\n2026-06-30 03:00:02.000,1\n', encoding='utf-8')
        publisher = MqttTagPublisher()
        publisher.mock_mode = True
        await publisher.start()
        sim = SimulatorEngine(publisher)
        cfg = ReplayConfig(csv_file='x.csv', csv_source='generated', frequency_hz=1, loop_mode='once', timestamp_mode='csv_timestamp_ignore_rate', start_row=0, tags=[TagMapping(enabled=True, csv_column='value', tag_name='Value', node_id='TagSimulator.Value', data_type='Int64')])
        await sim.configure(cfg)
        await sim.emit_once()

        assert sim.get_current_values().values[0].last_updated == '2026-06-30T03:00:02.000'

    asyncio.run(run())


def test_replay_configure_uses_managed_csv_manifest_for_colliding_id(tmp_path, monkeypatch):
    async def run() -> None:
        from app import csv_manager

        generated = tmp_path / "generated"
        datasets = generated / "datasets"
        generated.mkdir()
        datasets.mkdir()
        monkeypatch.setitem(csv_manager.SOURCE_DIRS, "generated", generated)
        monkeypatch.setattr(dataset_manager, "DATASET_DIR", datasets)
        csv_path = generated / "run_collision.csv"
        csv_path.write_text("timestamp,value\n2026-01-01T00:00:00Z,7\n", encoding="utf-8")
        dataset_manager.write_manifest(
            DatasetManifest(
                dataset_id="csv_generated_run_collision_csv",
                name="Friendly generated CSV",
                source="generated",
                storage_format="csv",
                state="ready",
                schema=[
                    DatasetSchemaField(name="timestamp", data_type="String"),
                    DatasetSchemaField(name="value", data_type="Int64"),
                ],
                row_count=1,
                column_count=2,
                ready_for_replay=True,
                path=str(csv_path),
            )
        )
        publisher = MqttTagPublisher()
        publisher.mock_mode = True
        await publisher.start()
        sim = SimulatorEngine(publisher)
        cfg = ReplayConfig(
            dataset_id="csv_generated_run_collision_csv",
            frequency_hz=1,
            loop_mode="once",
            timestamp_mode="wall_clock",
            tags=[TagMapping(enabled=True, csv_column="value", tag_name="Value", node_id="TagSimulator.Value", data_type="Int64")],
        )
        await sim.configure(cfg)
        await sim.emit_once()

        assert cfg.csv_file == "run_collision.csv"
        assert sim.row_count == 1
        assert sim.get_current_values().values[0].value == 7

    asyncio.run(run())


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
