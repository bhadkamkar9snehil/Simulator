from app.generators.petroleum_pipeline import PetroleumPipelineGenerator
from app.models import GenerateRequest


def test_small_leak_generates_imbalance():
    gen = PetroleumPipelineGenerator()
    rows = gen.generate(GenerateRequest(scenario='small_leak', output_filename='x.csv', parameters={'duration_minutes': 5, 'sample_rate_hz': 1, 'seed': 1}))
    assert rows
    assert {'flow_in_m3h','flow_out_m3h','leak_active','leak_alarm'} <= set(rows[0].keys())
    assert any(r['leak_active'] == 1 for r in rows)
    leak_rows = [r for r in rows if r['leak_active'] == 1]
    assert max(float(r['flow_imbalance_m3h']) for r in leak_rows) > 0


def test_pump_trip_changes_status():
    gen = PetroleumPipelineGenerator()
    rows = gen.generate(GenerateRequest(scenario='pump_trip', output_filename='x.csv', parameters={'duration_minutes': 5, 'sample_rate_hz': 1, 'seed': 1}))
    assert any(r['pump_1_status'] == 0 for r in rows)
