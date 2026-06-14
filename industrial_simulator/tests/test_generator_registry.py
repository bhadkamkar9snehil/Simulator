from app.generator_registry import list_generators, get_generator


def test_registry_contains_domains():
    ids = {g.domain_id for g in list_generators()}
    assert 'petroleum_pipeline' in ids
    assert 'eaf_melting' in ids
    assert get_generator('petroleum_pipeline').domain_id == 'petroleum_pipeline'
