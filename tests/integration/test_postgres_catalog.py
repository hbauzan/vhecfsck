"""Postgres catalog introspection tests (P7-04)."""

from __future__ import annotations

import pytest
from vhecfsck.adapters.postgres_adapter import metric_from_opclass
from vhecfsck.models import MetricSpace

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


@pytest.mark.parametrize(
    ("opc", "space"),
    [
        ("vector_l2_ops", MetricSpace.L2),
        ("vector_cosine_ops", MetricSpace.COSINE),
        ("vector_ip_ops", MetricSpace.DOT),
    ],
)
def test_opclass_metric_mapping(opc: str, space: MetricSpace) -> None:
    assert metric_from_opclass(opc) is space
