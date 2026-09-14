from __future__ import annotations

import pytest

from app.simulation.models import SignalDefinition, SignalMapping, SignalValue


def test_unified_signal_models_accept_canonical_scalar_and_array_types() -> None:
    assert SignalValue(value=[1, 2], data_type="UInt16[]").data_type == "UInt16[]"
    assert SignalDefinition(name="When", node_id="When", data_type="DateTime").data_type == "DateTime"
    assert SignalMapping(source="Samples", data_type="Array[Double]").data_type == "Array[Double]"


@pytest.mark.parametrize("model_factory", [
    lambda: SignalValue(value=1, data_type="Imaginary128"),
    lambda: SignalDefinition(name="X", node_id="X", data_type="Imaginary128"),
    lambda: SignalMapping(source="X", data_type="Imaginary128"),
])
def test_unified_signal_models_reject_unknown_datatypes(model_factory) -> None:
    with pytest.raises(ValueError, match="Unsupported OPC UA datatype"):
        model_factory()
