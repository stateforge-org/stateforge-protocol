"""Conformance evidence for scalar values shared by SFP procedures."""

from uuid import UUID

import pytest

from stateforge_protocol.sfp import primitives

_CANONICAL_UUID4 = "7f7db7d8-68b4-4f71-9769-065b5c4f941c"


def test_accepts_canonical_uuid4_and_uint32_boundaries() -> None:
    assert primitives.parse_canonical_uuid4(_CANONICAL_UUID4) == UUID(
        _CANONICAL_UUID4
    )
    assert primitives.is_canonical_uuid4(_CANONICAL_UUID4)
    assert primitives.is_uint32(0)
    assert primitives.is_uint32(primitives.PROTOBUF_UINT32_MAX)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        _CANONICAL_UUID4.upper(),
        "032d9b0e-fd9f-11f0-a2a2-0242ac120002",
        None,
    ],
)
def test_rejects_noncanonical_uuid4_values(value: object) -> None:
    with pytest.raises(
        primitives.ProtocolScalarError,
        match="canonical UUIDv4",
    ):
        primitives.parse_canonical_uuid4(value)
    assert not primitives.is_canonical_uuid4(value)


@pytest.mark.parametrize(
    "value",
    [-1, primitives.PROTOBUF_UINT32_MAX + 1, True, 1.0, "1"],
)
def test_rejects_values_outside_uint32(value: object) -> None:
    assert not primitives.is_uint32(value)
