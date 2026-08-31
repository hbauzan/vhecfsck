"""Unit tests for QdrantAdapter (P7-02) — no SDK required."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from vhecfsck.adapters.qdrant_adapter import (
    QdrantAdapter,
    deleted_from_telemetry,
    metric_from_qdrant_distance,
    parse_qdrant_target,
)
from vhecfsck.core.fragmentation import compute_dfi
from vhecfsck.errors import UsageError
from vhecfsck.models import IndexKind, MetricSpace, MetricState

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_SRC = ROOT / "vhecfsck" / "adapters" / "qdrant_adapter.py"

_MUTATING_SNIPPETS = (
    ".upsert(",
    ".upload_points(",
    ".upload_collection(",
    ".create_collection(",
    ".delete_collection(",
    ".update_collection(",
    ".set_payload(",
    ".overwrite_payload(",
    ".clear_payload(",
    ".update_vectors(",
    ".delete_vectors(",
    ".create_payload_index(",
    ".create_snapshot(",
)


class _FakePoint:
    def __init__(self, pid: int, vector: list[float], score: float = 0.1) -> None:
        self.id = pid
        self.vector = vector
        self.score = score


class _FakeClient:
    def __init__(
        self,
        *,
        dim: int = 4,
        distance: str = "Cosine",
        points: list[_FakePoint] | None = None,
        indexed: int | None = None,
        telemetry: object | None = None,
        payload_schema: dict[str, object] | None = None,
    ) -> None:
        rng = np.random.default_rng(0)
        if points is None:
            points = [
                _FakePoint(i, rng.normal(size=dim).astype(np.float32).tolist())
                for i in range(10)
            ]
        self.points = points
        self.telemetry_payload = telemetry
        vectors = SimpleNamespace(size=dim, distance=distance)
        hnsw = SimpleNamespace(m=16, ef_construct=64)
        schema = payload_schema if payload_schema is not None else {"color": {}}
        self._info = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(vectors=vectors),
                hnsw_config=hnsw,
            ),
            payload_schema=schema,
            points_count=len(points),
            indexed_vectors_count=len(points) if indexed is None else indexed,
        )
        self.closed = False

    def get_collection(self, name: str) -> object:
        assert name == "col"
        return self._info

    def count(self, collection_name: str, exact: bool = True) -> object:
        assert collection_name == "col"
        assert exact is True
        return SimpleNamespace(count=len(self.points))

    def telemetry(self, details_level: int = 0) -> object:
        del details_level
        if self.telemetry_payload is None:
            return {"app": "qdrant"}
        return self.telemetry_payload

    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        offset: object | None = None,
        **_kwargs: object,
    ) -> tuple[list[_FakePoint], int | None]:
        assert collection_name == "col"
        start = 0 if offset is None else int(offset)
        end = start + int(limit)
        chunk = self.points[start:end]
        nxt: int | None = end if end < len(self.points) else None
        return chunk, nxt

    def retrieve(
        self,
        *,
        collection_name: str,
        ids: list[object],
        **_kwargs: object,
    ) -> list[_FakePoint]:
        assert collection_name == "col"
        wanted = set(ids) | {str(i) for i in ids}
        return [p for p in self.points if p.id in wanted or str(p.id) in wanted]

    def query_points(
        self,
        *,
        collection_name: str,
        query: object,
        limit: int,
        **_kwargs: object,
    ) -> object:
        assert collection_name == "col"
        q = np.asarray(query, dtype=np.float32)
        ranked = sorted(
            self.points,
            key=lambda p: sum(
                (float(a) - float(b)) ** 2
                for a, b in zip(q.tolist(), p.vector, strict=True)
            ),
        )
        return SimpleNamespace(points=ranked[:limit])

    def close(self) -> None:
        self.closed = True


def _adapter(client: _FakeClient | None = None, **kwargs: object) -> QdrantAdapter:
    fake = client if client is not None else _FakeClient(**kwargs)
    return QdrantAdapter("qdrant://memory/col", client=fake)


def test_parse_remote_and_memory_and_path() -> None:
    remote = parse_qdrant_target("qdrant://localhost:6333/mycol")
    assert remote.mode == "remote"
    assert remote.host == "localhost"
    assert remote.port == 6333
    assert remote.collection == "mycol"
    mem = parse_qdrant_target("qdrant://memory/demo")
    assert mem.mode == "memory"
    assert mem.collection == "demo"
    path = parse_qdrant_target("qdrant:///?path=/tmp/qdrant&collection=c")
    assert path.mode == "path"
    assert path.path == "/tmp/qdrant"
    grpc = parse_qdrant_target(
        "qdrant://127.0.0.1:6333/c?prefer_grpc=true&api_key=s3cret"
    )
    assert grpc.prefer_grpc is True
    assert grpc.api_key == "s3cret"


def test_parse_requires_collection() -> None:
    with pytest.raises(UsageError):
        parse_qdrant_target("qdrant://localhost:6333")
    with pytest.raises(UsageError):
        parse_qdrant_target("")
    mem = parse_qdrant_target("qdrant://:memory:/demo")
    assert mem.mode == "memory"
    bad_grpc = parse_qdrant_target("qdrant://localhost:6333/c?grpc_port=nope")
    assert bad_grpc.grpc_port == 6334


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Cosine", MetricSpace.COSINE),
        ("EUCLID", MetricSpace.L2),
        ("Dot", MetricSpace.DOT),
    ],
)
def test_metric_from_distance(raw: str, expected: MetricSpace) -> None:
    assert metric_from_qdrant_distance(raw) is expected


def test_deleted_from_telemetry_sums_segments_or_none() -> None:
    assert deleted_from_telemetry({"app": "qdrant"}) is None
    payload = {
        "collections": {
            "collections": [
                {
                    "shards": [
                        {
                            "local": {
                                "segments": [
                                    {"info": {"num_deleted_vectors": 2}},
                                    {"info": {"num_deleted_vectors": 3}},
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    assert deleted_from_telemetry(payload) == 5


def test_descriptor_cosine_and_payload_fields() -> None:
    adapter = _adapter(distance="Cosine")
    try:
        desc = adapter.descriptor
        assert desc.engine == "qdrant"
        assert desc.index_kind is IndexKind.HNSW
        assert desc.metric_space is MetricSpace.COSINE
        assert adapter.dimension == 4
        assert adapter.payload_fields == ("color",)
        assert adapter.transport == "injected"
    finally:
        adapter.close()


@pytest.mark.parametrize("distance", ["Euclid", "Dot"])
def test_descriptor_euclid_and_dot(distance: str) -> None:
    adapter = _adapter(distance=distance)
    try:
        expected = MetricSpace.L2 if distance == "Euclid" else MetricSpace.DOT
        assert adapter.metric_space is expected
    finally:
        adapter.close()


def test_dfi_trap_does_not_use_indexed_gap() -> None:
    """points_count vs indexed_vectors_count is NOT deleted (spec §4.2)."""
    client = _FakeClient(indexed=6)
    assert client._info.points_count == 10
    assert client._info.indexed_vectors_count == 6
    adapter = _adapter(client)
    try:
        assert adapter.capabilities.report_deleted_counts is False
        counts = adapter.counts()
        assert counts.live == 10
        assert counts.deleted == 0
        assert counts.indexed == 6
        result = compute_dfi(
            counts,
            report_deleted_counts=adapter.capabilities.report_deleted_counts,
        )
        assert result.state is MetricState.UNAVAILABLE
        assert result.value is None
    finally:
        adapter.close()


def test_segment_telemetry_yields_exact_deleted() -> None:
    telemetry = {
        "collections": {
            "collections": [
                {
                    "shards": [
                        {"local": {"segments": [{"info": {"num_deleted_vectors": 4}}]}}
                    ]
                }
            ]
        }
    }
    adapter = _adapter(_FakeClient(telemetry=telemetry))
    try:
        assert adapter.capabilities.report_deleted_counts is True
        assert adapter.capabilities.deleted_counts_exact is True
        counts = adapter.counts()
        assert counts.deleted == 4
        assert counts.exact is True
        result = compute_dfi(
            counts,
            report_deleted_counts=True,
        )
        assert result.value is not None
        assert result.state is not MetricState.UNAVAILABLE
    finally:
        adapter.close()


def test_iter_fetch_search_and_readonly_counts() -> None:
    adapter = _adapter()
    try:
        before = adapter.counts()
        ids: list[int] = []
        for batch in adapter.iter_live_vectors(batch_size=3):
            ids.extend(int(x) for x in batch.ids)
        assert len(ids) == 10
        sample = adapter.sample_ids(4, seed=7)
        fetched = adapter.fetch_vectors(sample)
        assert fetched.ids.tobytes() == sample.tobytes()
        result = adapter.search(
            fetched.vectors[:2], 3, params={"ef_search": 16, "nprobe": 1}
        )
        assert result.ids.shape == (2, 3)
        assert result.effective_params["ef_search"] == 16
        assert result.effective_params["transport"] == "injected"
        after = adapter.counts()
        assert (before.live, before.deleted, before.total) == (
            after.live,
            after.deleted,
            after.total,
        )
        assert adapter.partitions() is None
        assert adapter.graph_stats() is None
    finally:
        adapter.close()


def test_graph_stats_returns_none_and_capability_is_false() -> None:
    """Qdrant exposes no HNSW graph introspection API (ticket P7-06)."""
    adapter = _adapter()
    try:
        assert adapter.capabilities.report_graph_stats is False
        assert adapter.graph_stats() is None
    finally:
        adapter.close()


def test_close_blocks_use() -> None:
    adapter = _adapter()
    adapter.close()
    adapter.close()
    with pytest.raises(UsageError):
        adapter.counts()


def test_adapter_source_has_no_mutating_calls() -> None:
    text = ADAPTER_SRC.read_text(encoding="utf-8")
    for snippet in _MUTATING_SNIPPETS:
        assert snippet not in text, snippet


def test_deleted_from_telemetry_model_dump() -> None:
    class _Node:
        def model_dump(self) -> dict[str, int]:
            return {"num_deleted_vectors": 2}

    assert deleted_from_telemetry(_Node()) == 2


def test_batch_size_and_search_guards() -> None:
    adapter = _adapter()
    try:
        with pytest.raises(UsageError, match="batch_size"):
            next(adapter.iter_live_vectors(batch_size=0))
        empty = adapter.fetch_vectors(np.empty(0, dtype=np.int64))
        assert empty.ids.shape[0] == 0
        with pytest.raises(UsageError, match="k must"):
            adapter.search(np.zeros((1, 4), dtype=np.float32), 0, params={})
        with pytest.raises(UsageError, match="float32"):
            adapter.search(np.zeros((1, 4), dtype=np.float64), 1, params={})
        with pytest.raises(UsageError, match="shape"):
            adapter.search(np.zeros((1, 3), dtype=np.float32), 1, params={})
        with pytest.raises(UsageError, match="unknown vector id"):
            adapter.fetch_vectors(np.array([999], dtype=np.int64))
    finally:
        adapter.close()


def test_legacy_search_api_and_missing_read_api() -> None:
    class _Legacy(_FakeClient):
        @property
        def query_points(self) -> None:  # type: ignore[override]
            return None

        def search(
            self,
            *,
            collection_name: str,
            query_vector: object,
            limit: int,
            **_kwargs: object,
        ) -> list[_FakePoint]:
            result = super().query_points(
                collection_name=collection_name, query=query_vector, limit=limit
            )
            return list(result.points)

    adapter = _adapter(_Legacy())
    try:
        q = np.zeros((1, 4), dtype=np.float32)
        result = adapter.search(q, 2, params={"ef_search": 8, "nprobe": 1})
        assert result.ids.shape == (1, 2)
    finally:
        adapter.close()

    class _Blind(_FakeClient):
        @property
        def query_points(self) -> None:  # type: ignore[override]
            return None

        @property
        def search(self) -> None:
            return None

    adapter = _adapter(_Blind())
    try:
        with pytest.raises(UsageError, match="query_points/search"):
            adapter.search(np.zeros((1, 4), dtype=np.float32), 1, params={})
    finally:
        adapter.close()


def test_named_vector_and_dict_payload_schema() -> None:
    client = _FakeClient()
    named = SimpleNamespace(size=4, distance="Cosine")
    client._info.config.params.vectors = {"dense": named}
    adapter = QdrantAdapter("qdrant://memory/col?vector=dense", client=client)
    try:
        assert adapter.dimension == 4
        rec = _FakePoint(0, [0.0, 1.0, 0.0, 0.0])
        rec.vector = {"dense": rec.vector}
        ids, vecs = adapter._records_to_batch([rec])
        assert ids[0] == 0
        assert vecs.shape == (1, 4)
    finally:
        adapter.close()

    client2 = _FakeClient(payload_schema=["not", "a", "dict"])
    adapter2 = _adapter(client2)
    try:
        assert adapter2.payload_fields == ()
    finally:
        adapter2.close()


def test_telemetry_kwargs_fallback_and_failure() -> None:
    class _NoKwargs(_FakeClient):
        def telemetry(self) -> object:  # type: ignore[override]
            return {
                "collections": {
                    "collections": [
                        {
                            "shards": [
                                {
                                    "local": {
                                        "segments": [
                                            {"info": {"num_deleted_vectors": 1}}
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            }

    adapter = _adapter(_NoKwargs())
    try:
        assert adapter.capabilities.report_deleted_counts is True
        assert adapter.counts().deleted == 1
    finally:
        adapter.close()

    class _Broken(_FakeClient):
        def telemetry(self, **_kwargs: object) -> object:
            raise RuntimeError("telemetry down")

    adapter = _adapter(_Broken())
    try:
        assert adapter.capabilities.report_deleted_counts is False
    finally:
        adapter.close()


def test_count_fallback_and_get_collection_failure() -> None:
    class _CountFails(_FakeClient):
        def count(self, collection_name: str, exact: bool = True) -> object:
            del collection_name, exact
            raise RuntimeError("count down")

        def get_collection(self, name: str) -> object:
            del name
            return self._info

    adapter = _adapter(_CountFails())
    try:
        assert adapter.counts().live == 10
    finally:
        adapter.close()

    class _Missing(_FakeClient):
        def get_collection(self, name: str) -> object:
            del name
            raise RuntimeError("no such collection")

    with pytest.raises(UsageError, match="failed to read"):
        QdrantAdapter("qdrant://memory/col", client=_Missing())


def test_connect_memory_http_grpc_and_grpc_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []

    class _SdkClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            created.append({"args": args, "kwargs": kwargs})
            if kwargs.get("prefer_grpc") is True and kwargs.get("host") == "fail.grpc":
                raise OSError("grpc unavailable")
            self._info = _FakeClient()._info

        def get_collection(self, name: str) -> object:
            del name
            return self._info

        def telemetry(self, details_level: int = 0) -> object:
            del details_level
            return {"app": "qdrant"}

        def close(self) -> None:
            return None

    fake_mod = SimpleNamespace(QdrantClient=_SdkClient, __version__="1.19.0")

    def _import(name: str, *_args: object, **_kwargs: object) -> object:
        if name == "qdrant_client":
            return fake_mod
        raise ImportError(name)

    monkeypatch.setattr(
        "vhecfsck.adapters.qdrant_adapter.importlib.import_module", _import
    )

    mem = QdrantAdapter("qdrant://memory/col")
    try:
        assert mem.transport == "local"
        assert created[-1]["args"] == (":memory:",)
    finally:
        mem.close()

    path = QdrantAdapter("qdrant:///?path=/tmp/qstore&collection=col")
    try:
        assert path.transport == "local"
        assert created[-1]["kwargs"]["path"] == "/tmp/qstore"
    finally:
        path.close()

    http = QdrantAdapter("qdrant://localhost:6333/col")
    try:
        assert http.transport == "http"
        assert created[-1]["kwargs"]["prefer_grpc"] is False
    finally:
        http.close()

    grpc = QdrantAdapter("qdrant://localhost:6333/col?prefer_grpc=true")
    try:
        assert grpc.transport == "grpc"
        assert created[-1]["kwargs"]["prefer_grpc"] is True
    finally:
        grpc.close()

    with pytest.warns(UserWarning, match="gRPC failed"):
        fallback = QdrantAdapter("qdrant://fail.grpc:6333/col?prefer_grpc=true")
    try:
        assert fallback.transport == "http"
    finally:
        fallback.close()


def test_uuid_ids_round_trip() -> None:
    points = [
        _FakePoint("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", [1.0, 0.0, 0.0, 0.0]),
        _FakePoint("11111111-2222-3333-4444-555555555555", [0.0, 1.0, 0.0, 0.0]),
    ]
    adapter = _adapter(_FakeClient(points=points))
    try:
        ids: list[int] = []
        for batch in adapter.iter_live_vectors(batch_size=1):
            ids.extend(int(x) for x in batch.ids)
        assert len(ids) == 2
        fetched = adapter.fetch_vectors(np.array(ids, dtype=np.int64))
        assert fetched.vectors.shape == (2, 4)
    finally:
        adapter.close()
