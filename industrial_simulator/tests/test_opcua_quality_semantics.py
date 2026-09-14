from __future__ import annotations

import pytest

from app.opcua_support import status_code as support_status_code
from app.opcua_types import status_code as canonical_status_code

try:
    from asyncua import ua
except Exception:  # pragma: no cover
    ua = None


@pytest.mark.skipif(ua is None, reason="asyncua not installed")
def test_legacy_and_unified_status_code_surfaces_use_same_named_semantics() -> None:
    expected = ua.StatusCodes.BadNoData
    assert canonical_status_code("BadNoData").value == expected
    assert support_status_code("BadNoData").value == expected


@pytest.mark.skipif(ua is None, reason="asyncua not installed")
def test_numeric_status_codes_are_preserved_exactly() -> None:
    expected = ua.StatusCodes.BadCommunicationError
    assert canonical_status_code(expected).value == expected
    assert support_status_code(expected).value == expected
    assert canonical_status_code(hex(expected)).value == expected


@pytest.mark.skipif(ua is None, reason="asyncua not installed")
def test_unknown_status_code_never_falls_back_to_good() -> None:
    with pytest.raises(ValueError, match="Unknown OPC UA quality/status code"):
        canonical_status_code("DefinitelyNotAStatusCode")
    with pytest.raises(ValueError, match="Unknown OPC UA quality/status code"):
        support_status_code("DefinitelyNotAStatusCode")
