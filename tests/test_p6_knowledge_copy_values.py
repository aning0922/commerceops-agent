"""Independent float32 wire and numerical safety goldens. No PG/model/provider calls."""

import math
import struct
from typing import Any

import pytest
from commerceops.infrastructure.knowledge_copy_values import (
    PgEvidence,
    f32_vector,
    pg_digest,
    pg_profile,
    query_parameter,
    vector_bytes,
    vector_parameter,
)

from tests.test_p6_knowledge_copy_contracts import embedding, profile, query

pytestmark = pytest.mark.offline


def test_float32_wire_has_dimension_unused_and_network_endianness() -> None:
    assert vector_bytes((1.0, -2.0)).hex() == "000200003f800000c0000000"
    assert vector_bytes((1.0, -0.0)).hex() == "000200003f80000000000000"
    assert vector_parameter((0.1, 1.0)) == "[0.100000001,1]"
    assert f32_vector((0.1, 1.0)) == (struct.unpack("!f", bytes.fromhex("3dcccccd"))[0], 1.0)


@pytest.mark.parametrize(
    "values",
    [
        (),
        (0.0, 0.0),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (True, 1.0),
        (1e38, 1e38),
        (1e20, 1.0),
        (1e-30, 1.0),
        (1e-30, 1e-30),
        (1e-100, 1.0),
        (1e-7, 1.0),
        (1e6, 1e6),
        (1.0, 0),
    ],
)
def test_extremes_rejected_before_pg_can_clamp_inf_or_hide_underflow(
    values: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        f32_vector(values)


def test_safe_nonzero_components_and_profile_binding() -> None:
    assert f32_vector((0.0, 1e6)) == (0.0, 1e6)
    assert math.isclose(f32_vector((2e-6, 0.0))[0], 2e-6, rel_tol=1e-7)
    pg = pg_profile(profile().profile_digest, 2)
    assert str(pg.distance_version) != str(profile().distance_version)
    assert query_parameter(query(), pg) == "[1,0]"
    with pytest.raises(ValueError):
        query_parameter(query(), pg_profile("0" * 64, 2))


def test_stored_evidence_cannot_bless_changed_binary_or_reference_distance() -> None:
    original = embedding(vector=(3.0, 4.0))
    prof = pg_profile(original.profile.profile_digest, 2)
    raw = bytes.fromhex("000200004040000040800000")
    fields: dict[str, Any] = dict(
        origin=original,
        profile=prof,
        stored_hex=raw.hex(),
        query=query(),
        stored_sha256=pg_digest(prof.profile_digest, original.citation.evidence_id, raw),
        distance=0.4,
        reference_distance=0.4,
    )
    evidence = PgEvidence.model_validate(fields)
    assert evidence.distance == 0.4
    assert PgEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    for changes in (
        {"stored_hex": "000200000000000000000000"},
        {"stored_sha256": "0" * 64},
        {"reference_distance": 0.3},
        {"distance": 0.3},
    ):
        with pytest.raises(ValueError):
            PgEvidence.model_validate(fields | changes)


def test_clamped_valid_looking_pg_distance_does_not_admit_extreme_source() -> None:
    original = embedding(vector=(1e38, 1e38))
    prof = pg_profile(original.profile.profile_digest, 2)
    with pytest.raises(ValueError, match="KNOWLEDGE_NUMERIC_POLICY"):
        PgEvidence(
            origin=original,
            profile=prof,
            stored_hex="00",
            stored_sha256="0" * 64,
            distance=0.0,
            query=query(),
            reference_distance=0.0,
        )


def test_pg_result_rebuilds_hits_scope_count_and_mode() -> None:
    from uuid import UUID

    from commerceops.infrastructure.knowledge_copy_values import PgRetrieval

    from tests.test_p6_knowledge_copy_contracts import NOW, SCOPE, changed, seal

    original = embedding(vector=(3.0, 4.0))
    prof = pg_profile(original.profile.profile_digest, 2)
    raw = bytes.fromhex("000200004040000040800000")
    evidence = PgEvidence(
        origin=original,
        profile=prof,
        stored_hex=raw.hex(),
        query=query(),
        stored_sha256=pg_digest(prof.profile_digest, original.citation.evidence_id, raw),
        distance=0.4,
        reference_distance=0.4,
    )
    # Pure receipt fixture, not a claim that SQL returned this row.
    value = seal(
        PgRetrieval,
        "result_hash",
        scope=SCOPE,
        registry_id=UUID(int=1),
        registry_version="pure-fixture-v1",
        registry_digest="0" * 64,
        profile=prof,
        query=query(),
        as_of=NOW,
        eligible_count=1,
        pool=(evidence,),
        hits=(),
        max_distance=0.35,
        reason="INSUFFICIENT_EVIDENCE",
    )
    assert PgRetrieval.model_validate_json(value.model_dump_json()) == value
    for updates in (
        {"hits": (original.citation,), "reason": "OK"},
        {"eligible_count": 0},
        {"evidence_mode": "actual_provider"},
        {"complete": False},
        {"reason": "OK"},
        {"as_of": NOW.replace(year=2027)},
    ):
        with pytest.raises(ValueError):
            changed(value, "result_hash", **updates)
