from app.type_inference import infer_column_type, convert_value, sanitize_tag_name


def test_infer_numeric_types():
    assert infer_column_type('pressure', ['1.2','2.5']) == 'Double'
    assert infer_column_type('count', ['1','2']) == 'Int64'


def test_infer_boolean_suffix():
    assert infer_column_type('leak_alarm', ['0','1','0']) == 'Boolean'


def test_convert_value():
    assert convert_value('1.5', 'Double') == 1.5
    assert convert_value('1', 'Boolean') is True
    assert convert_value('abc', 'String') == 'abc'


def test_sanitize_tag_name():
    assert sanitize_tag_name('Flow In (m3/h)') == 'Flow_In_m3_h'
