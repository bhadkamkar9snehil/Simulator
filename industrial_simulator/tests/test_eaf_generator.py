from app.generators.eaf_melting import EafMeltingGenerator
from app.models import GenerateRequest


def test_eaf_generates_phases():
    gen = EafMeltingGenerator()
    rows = gen.generate(GenerateRequest(scenario='unstable_arc', output_filename='x.csv', parameters={'duration_minutes': 20, 'sample_rate_hz': 1, 'seed': 1}))
    assert rows
    phases = {r['phase'] for r in rows}
    assert 'melting' in phases
    assert any(r['unstable_arc_active'] == 1 for r in rows)
