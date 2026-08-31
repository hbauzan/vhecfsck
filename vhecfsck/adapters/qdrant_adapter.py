"""Qdrant read-only IndexAdapter (P7-02).

Local/embedded (``:memory:`` / ``path=``) and remote HTTP/gRPC. Deleted counts
come from per-segment telemetry only — never from ``points_count`` versus
``indexed_vectors_count`` (metrics spec §4.2).
"""

from __future__ import annotations

import contextlib
import importlib
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import numpy as np
from numpy.random import default_rng

from vhecfsck.adapters.base import (
    FloatMatrix,
    IdArray,
    SearchParams,
    StringIdMapper,
)
from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets
from vhecfsck.models import (
    Capabilities,
    GraphStats,
    IndexCounts,
    IndexKind,
    MetricSpace,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)

_MEMORY_NETLOCS = frozenset({"memory", ":memory:", "embedded", "local"})
_GRPC_DEFAULT = 6334
_HTTP_DEFAULT = 6333


@dataclass(frozen=True)
class QdrantTarget:
    """Parsed ``qdrant://`` URI."""

    collection: str
    mode: Literal["memory", "path", "remote"]
    host: str | None
    port: int | None
    path: str | None
    api_key: str | None
    prefer_grpc: bool
    grpc_port: int
    vector_name: str | None


def parse_qdrant_target(target: str) -> QdrantTarget:
    """Parse ``qdrant://host:port/collection`` / memory / path URIs."""
    raw = target.strip()
    if not raw:
        raise UsageError("qdrant target must be non-empty")
    parsed = urlparse(raw if "://" in raw else f"qdrant://{raw}")
    qs = parse_qs(parsed.query)
    collection = (qs.get("collection", [""])[0] or parsed.path.strip("/")).strip()
    if "/" in collection:
        collection = collection.rsplit("/", 1)[-1]
    if not collection:
        raise UsageError(
            "qdrant target requires a collection name",
            hint="example: qdrant://localhost:6333/mycollection",
        )
    path = qs.get("path", [None])[0]
    api_key = qs.get("api_key", qs.get("api-key", [None]))[0]
    prefer_raw = qs.get("prefer_grpc", ["false"])[0].lower()
    prefer_grpc = prefer_raw in {"1", "true", "yes"}
    grpc_raw = qs.get("grpc_port", [str(_GRPC_DEFAULT)])[0]
    try:
        grpc_port = int(grpc_raw)
    except ValueError:
        grpc_port = _GRPC_DEFAULT
    vector_name = qs.get("vector", [None])[0]
    netloc = (parsed.netloc or "").lower()
    try:
        hostname = (parsed.hostname or "").lower()
    except ValueError:
        hostname = ""
    if path:
        return QdrantTarget(
            collection=collection,
            mode="path",
            host=None,
            port=None,
            path=path,
            api_key=api_key,
            prefer_grpc=False,
            grpc_port=grpc_port,
            vector_name=vector_name,
        )
    if hostname in _MEMORY_NETLOCS or netloc in _MEMORY_NETLOCS:
        return QdrantTarget(
            collection=collection,
            mode="memory",
            host=None,
            port=None,
            path=None,
            api_key=api_key,
            prefer_grpc=False,
            grpc_port=grpc_port,
            vector_name=vector_name,
        )
    host = hostname or "localhost"
    port = parsed.port or _HTTP_DEFAULT
    return QdrantTarget(
        collection=collection,
        mode="remote",
        host=host,
        port=int(port),
        path=None,
        api_key=api_key,
        prefer_grpc=prefer_grpc,
        grpc_port=grpc_port,
        vector_name=vector_name,
    )


def metric_from_qdrant_distance(value: object) -> MetricSpace:
    """Map Qdrant distance name/enum to ``MetricSpace``."""
    text = str(getattr(value, "value", value)).upper()
    if "COSINE" in text:
        return MetricSpace.COSINE
    if "DOT" in text:
        return MetricSpace.DOT
    return MetricSpace.L2


def deleted_from_telemetry(payload: object) -> int | None:
    """Sum per-segment ``num_deleted_vectors``.

    Returns ``None`` when that field never appears — the caller must then
    leave ``report_deleted_counts`` false rather than substitute
    ``points_count - indexed_vectors_count``.
    """
    found = False
    total = 0

    def _walk(node: object) -> None:
        nonlocal found, total
        if isinstance(node, dict):
            if "num_deleted_vectors" in node:
                found = True
                with contextlib.suppress(TypeError, ValueError):
                    total += int(node["num_deleted_vectors"] or 0)
            for child in node.values():
                _walk(child)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                _walk(child)
            return
        dump = getattr(node, "model_dump", None) or getattr(node, "dict", None)
        if callable(dump):
            _walk(dump())

    _walk(payload)
    return total if found else None


class QdrantAdapter:
    """Read-only window onto a Qdrant collection."""

    def __init__(self, target: str, *, client: Any | None = None) -> None:
        parsed = parse_qdrant_target(target)
        self._target = target
        self._parsed = parsed
        self._collection = parsed.collection
        self._closed = False
        self._ids = StringIdMapper()
        self._transport = "local"
        self._engine_version = "unknown"
        self._vector_name = parsed.vector_name
        self._client: Any
        if client is None:
            self._client, self._transport, self._engine_version = self._connect(parsed)
        else:
            self._client = client
            self._transport = "injected"
            self._engine_version = str(
                getattr(client, "_version", None)
                or getattr(getattr(client, "__class__", None), "__module__", "injected")
            )
        self._info = self._load_collection_info()
        self._dimension_val, self._metric_val, self._hnsw_ef_construct = (
            self._vector_meta(self._info)
        )
        self._payload_fields = self._payload_field_names(self._info)
        deleted = self._segment_deleted()
        self._deleted_known = deleted is not None
        self._deleted_cached = int(deleted) if deleted is not None else 0
        self._capabilities_val = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=self._deleted_known,
            deleted_counts_exact=self._deleted_known,
            report_partitions=False,
            partition_live_counts=False,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=True,
        )

    def _connect(self, parsed: QdrantTarget) -> tuple[Any, str, str]:
        try:
            qdrant_client = importlib.import_module("qdrant_client")
        except ImportError as exc:
            safe = redact_secrets(self._target)
            raise UsageError(
                f"Qdrant support is not installed (target={safe})",
                hint='pip install "vhecfsck[qdrant]"',
            ) from exc
        client_cls = qdrant_client.QdrantClient
        version = str(getattr(qdrant_client, "__version__", "unknown"))
        if parsed.mode == "memory":
            return client_cls(":memory:"), "local", version
        if parsed.mode == "path":
            return client_cls(path=parsed.path), "local", version
        kwargs: dict[str, Any] = {
            "host": parsed.host,
            "port": parsed.port,
            "api_key": parsed.api_key,
        }
        if parsed.prefer_grpc:
            try:
                return (
                    client_cls(
                        **kwargs,
                        prefer_grpc=True,
                        grpc_port=parsed.grpc_port,
                    ),
                    "grpc",
                    version,
                )
            except Exception as exc:
                warnings.warn(
                    f"Qdrant gRPC failed ({redact_secrets(type(exc).__name__)}); "
                    "falling back to HTTP",
                    UserWarning,
                    stacklevel=2,
                )
        return client_cls(**kwargs, prefer_grpc=False), "http", version

    def _load_collection_info(self) -> Any:
        try:
            return self._client.get_collection(self._collection)
        except Exception as exc:
            safe = redact_secrets(self._target)
            raise UsageError(
                f"failed to read Qdrant collection {self._collection!r} "
                f"(target={safe}): {redact_secrets(str(exc))}",
                hint="check the collection name and that the instance is reachable",
            ) from exc

    def _vector_meta(self, info: Any) -> tuple[int, MetricSpace, int | None]:
        params = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(params, "vectors", None)
        chosen: Any = None
        if vectors is not None and hasattr(vectors, "size"):
            chosen = vectors
        elif isinstance(vectors, dict):
            if self._vector_name is not None:
                if self._vector_name not in vectors:
                    raise UsageError(
                        f"named vector {self._vector_name!r} not in collection",
                        hint=f"available: {sorted(vectors)}",
                    )
                chosen = vectors[self._vector_name]
            elif len(vectors) == 1:
                chosen = next(iter(vectors.values()))
                self._vector_name = next(iter(vectors.keys()))
            else:
                raise UsageError(
                    f"multiple named vectors: {sorted(vectors)}; pass ?vector=",
                    hint="example: qdrant://localhost:6333/col?vector=dense",
                )
        if chosen is None:
            raise UsageError("collection does not expose vector parameters")
        dim = int(getattr(chosen, "size", 0) or 0)
        if dim < 1:
            raise UsageError("collection vector size is missing")
        metric = metric_from_qdrant_distance(getattr(chosen, "distance", "Euclid"))
        hnsw = getattr(getattr(info, "config", None), "hnsw_config", None)
        ef_c = getattr(hnsw, "ef_construct", None)
        ef_construct = int(ef_c) if ef_c is not None else None
        return dim, metric, ef_construct

    def _payload_field_names(self, info: Any) -> tuple[str, ...]:
        schema = getattr(info, "payload_schema", None) or {}
        if isinstance(schema, dict):
            return tuple(sorted(str(k) for k in schema))
        return ()

    def _segment_deleted(self) -> int | None:
        telemetry_fn = getattr(self._client, "telemetry", None)
        if not callable(telemetry_fn):
            return None
        try:
            payload = telemetry_fn(details_level=4)
        except TypeError:
            try:
                payload = telemetry_fn()
            except Exception:
                return None
        except Exception:
            return None
        return deleted_from_telemetry(payload)

    def _ensure_open(self) -> None:
        if self._closed:
            raise UsageError("adapter is closed")

    def _encode_id(self, raw: object) -> int:
        if isinstance(raw, (int, np.integer)) and not isinstance(raw, bool):
            return int(raw)
        encoded = self._ids.encode([str(raw)])
        return int(encoded[0])

    def _decode_id(self, vid: int) -> object:
        try:
            token = self._ids.decode(np.array([vid], dtype=np.int64))[0]
        except IndexError:
            return vid
        if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
            return int(token)
        return token

    @property
    def descriptor(self) -> TargetDescriptor:
        self._ensure_open()
        return TargetDescriptor(
            engine="qdrant",
            engine_version=self._engine_version,
            index_kind=IndexKind.HNSW,
            index_name=self._collection,
            location=redact_secrets(self._target),
            dimension=self._dimension_val,
            metric_space=self._metric_val,
        )

    @property
    def capabilities(self) -> Capabilities:
        self._ensure_open()
        return self._capabilities_val

    @property
    def dimension(self) -> int:
        self._ensure_open()
        return self._dimension_val

    @property
    def metric_space(self) -> MetricSpace:
        self._ensure_open()
        return self._metric_val

    @property
    def payload_fields(self) -> tuple[str, ...]:
        """Payload schema field names reported by the collection (may be empty)."""
        self._ensure_open()
        return self._payload_fields

    @property
    def transport(self) -> str:
        """``local`` / ``http`` / ``grpc`` / ``injected``."""
        self._ensure_open()
        return self._transport

    def counts(self) -> IndexCounts:
        self._ensure_open()
        live = self._point_count()
        indexed = self._indexed_count(live)
        deleted = self._deleted_cached if self._deleted_known else 0
        total = live + deleted if self._deleted_known else live
        return IndexCounts(
            live=live,
            deleted=deleted,
            total=total,
            indexed=indexed,
            degenerate=0,
            exact=self._deleted_known,
            read_at=datetime.now(tz=UTC),
        )

    def _point_count(self) -> int:
        count_fn = getattr(self._client, "count", None)
        if callable(count_fn):
            try:
                result = count_fn(self._collection, exact=True)
                value = getattr(result, "count", result)
                return int(value)
            except Exception:
                pass
        info = self._load_collection_info()
        pts = getattr(info, "points_count", None)
        return int(pts) if pts is not None else 0

    def _indexed_count(self, live: int) -> int:
        info = self._info
        indexed = getattr(info, "indexed_vectors_count", None)
        if indexed is None:
            return live
        return int(indexed)

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        self._ensure_open()
        if batch_size < 1:
            raise UsageError("batch_size must be >= 1")
        offset: object | None = None
        while True:
            records, offset = self._scroll(
                limit=batch_size, offset=offset, vectors=True
            )
            if not records:
                break
            ids, vectors = self._records_to_batch(records)
            yield VectorBatch(ids=ids, vectors=vectors)
            if offset is None:
                break

    def _scroll(
        self,
        *,
        limit: int,
        offset: object | None,
        vectors: bool,
        payload: bool = False,
    ) -> tuple[list[Any], object | None]:
        kwargs: dict[str, Any] = {
            "collection_name": self._collection,
            "limit": limit,
            "with_vectors": vectors,
            "with_payload": payload,
        }
        if offset is not None:
            kwargs["offset"] = offset
        result = self._client.scroll(**kwargs)
        if isinstance(result, tuple) and len(result) == 2:
            points, next_offset = result
            return list(points or []), next_offset
        points = getattr(result, "points", result)
        next_offset = getattr(result, "next_page_offset", None)
        return list(points or []), next_offset

    def _extract_vector(self, record: Any) -> np.ndarray:
        raw = getattr(record, "vector", None)
        if isinstance(raw, dict):
            if self._vector_name and self._vector_name in raw:
                raw = raw[self._vector_name]
            elif len(raw) == 1:
                raw = next(iter(raw.values()))
        if raw is None:
            msg = "scroll/retrieve returned a point without a vector"
            raise UsageError(msg)
        return np.asarray(raw, dtype=np.float32)

    def _records_to_batch(self, records: list[Any]) -> tuple[IdArray, FloatMatrix]:
        ids_list: list[int] = []
        vecs: list[np.ndarray] = []
        for rec in records:
            ids_list.append(self._encode_id(getattr(rec, "id", None)))
            vecs.append(self._extract_vector(rec))
        ids = np.ascontiguousarray(np.array(ids_list, dtype=np.int64))
        if not vecs:
            vectors = np.empty((0, self._dimension_val), dtype=np.float32)
        else:
            vectors = np.ascontiguousarray(np.stack(vecs, axis=0).astype(np.float32))
        return ids, vectors

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        self._ensure_open()
        collected: list[int] = []
        offset: object | None = None
        while True:
            records, offset = self._scroll(limit=256, offset=offset, vectors=False)
            if not records:
                break
            for rec in records:
                collected.append(self._encode_id(getattr(rec, "id", None)))
            if offset is None:
                break
        if not collected:
            return np.empty(0, dtype=np.int64)
        arr = np.ascontiguousarray(np.array(collected, dtype=np.int64))
        take = min(int(n), int(arr.shape[0]))
        if take == int(arr.shape[0]):
            return arr
        rng = default_rng(seed)
        chosen = rng.choice(arr, size=take, replace=False)
        return np.ascontiguousarray(chosen, dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        self._ensure_open()
        if ids.shape[0] == 0:
            return VectorBatch(
                ids=np.ascontiguousarray(ids, dtype=np.int64),
                vectors=np.empty((0, self._dimension_val), dtype=np.float32),
            )
        raw_ids = [self._decode_id(int(i)) for i in ids]
        records = list(
            self._client.retrieve(
                collection_name=self._collection,
                ids=raw_ids,
                with_vectors=True,
                with_payload=False,
            )
        )
        by_id: dict[int, np.ndarray] = {}
        for rec in records:
            by_id[self._encode_id(getattr(rec, "id", None))] = self._extract_vector(rec)
        vecs = np.empty((ids.shape[0], self._dimension_val), dtype=np.float32)
        for i, vid in enumerate(ids):
            vec = by_id.get(int(vid))
            if vec is None:
                raise UsageError(f"unknown vector id: {int(vid)}")
            vecs[i] = vec
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=np.ascontiguousarray(vecs),
        )

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        self._ensure_open()
        if k < 1:
            raise UsageError("k must be >= 1")
        if not isinstance(queries, np.ndarray) or queries.dtype != np.float32:
            raise UsageError("queries must be float32")
        if queries.ndim != 2 or queries.shape[1] != self._dimension_val:
            raise UsageError("queries must have shape (q, dimension)")
        nprobe = int(params.get("nprobe", 1))
        ef_search = int(params.get("ef_search", max(k, 1)))
        qn = int(queries.shape[0])
        out_ids = np.full((qn, k), -1, dtype=np.int64)
        out_dist = np.full((qn, k), np.nan, dtype=np.float32)
        search_kwargs = self._search_kwargs(ef_search)
        filt = params.get("filter")
        if filt:
            if not isinstance(filt, dict):
                raise UsageError(
                    "search filter must be a dict with key and value",
                    hint='pass filter={"key": "tenant_id", "value": "t0"}',
                )
            search_kwargs["query_filter"] = self._as_query_filter(filt)
        for qi in range(qn):
            hits = self._query_one(queries[qi], k, search_kwargs)
            for hi, hit in enumerate(hits[:k]):
                out_ids[qi, hi] = self._encode_id(getattr(hit, "id", None))
                score = getattr(hit, "score", None)
                if score is not None:
                    out_dist[qi, hi] = np.float32(score)
        effective: dict[str, object] = {
            "nprobe": nprobe,
            "ef_search": ef_search,
            "transport": self._transport,
        }
        if self._hnsw_ef_construct is not None:
            effective["ef_construct"] = self._hnsw_ef_construct
        if filt:
            effective["filter"] = dict(filt)
        return SearchResult(
            ids=out_ids,
            distances=out_dist,
            effective_params=effective,
        )

    def _search_kwargs(self, ef_search: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        try:
            models = importlib.import_module("qdrant_client.http.models")
            params_cls = getattr(models, "SearchParams", None)
            if params_cls is not None:
                kwargs["search_params"] = params_cls(hnsw_ef=ef_search)
        except Exception:
            kwargs["search_params"] = {"hnsw_ef": ef_search}
        if self._vector_name:
            kwargs["using"] = self._vector_name
        return kwargs

    def _as_query_filter(self, spec: dict[str, object]) -> Any:
        key = str(spec.get("key", ""))
        if not key:
            raise UsageError(
                "search filter requires a payload field name",
                hint='pass filter={"key": "tenant_id", "value": "t0"}',
            )
        try:
            models = importlib.import_module("qdrant_client.http.models")
            return models.Filter(
                must=[
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=spec.get("value")),
                    )
                ]
            )
        except Exception:
            return {"key": key, "value": spec.get("value")}

    def payload_values(self, field: str) -> dict[int, object]:
        """Map encoded live ids to ``field`` payload values (scroll, read-only)."""
        self._ensure_open()
        if not field:
            raise UsageError(
                "payload field name must be non-empty",
                hint="example: tenant_id",
            )
        out: dict[int, object] = {}
        offset: object | None = None
        while True:
            records, offset = self._scroll(
                limit=256, offset=offset, vectors=False, payload=True
            )
            if not records:
                break
            for rec in records:
                payload = getattr(rec, "payload", None) or {}
                if not isinstance(payload, dict):
                    continue
                if field not in payload:
                    continue
                out[self._encode_id(getattr(rec, "id", None))] = payload[field]
            if offset is None:
                break
        return out

    def _query_one(
        self, query: np.ndarray, k: int, search_kwargs: dict[str, Any]
    ) -> list[Any]:
        vector = query.tolist()
        query_points = getattr(self._client, "query_points", None)
        if callable(query_points):
            result = query_points(
                collection_name=self._collection,
                query=vector,
                limit=k,
                with_payload=False,
                with_vectors=False,
                **search_kwargs,
            )
            points = getattr(result, "points", result)
            return list(points or [])
        search_fn = getattr(self._client, "search", None)
        if not callable(search_fn):
            raise UsageError("Qdrant client has no query_points/search read API")
        result = search_fn(
            collection_name=self._collection,
            query_vector=vector,
            limit=k,
            with_payload=False,
            with_vectors=False,
            **search_kwargs,
        )
        return list(result or [])

    def partitions(self) -> PartitionStats | None:
        self._ensure_open()
        return None

    def graph_stats(self) -> GraphStats | None:
        """HNSW graph statistics (histogram, entry points, tombstone).

        Unavailable for Qdrant: neither qdrant-client 1.12+ nor Qdrant server
        v1.19.0 telemetry / REST / gRPC expose internal HNSW graph structure,
        entry point IDs, or entrypoint tombstone status.
        """
        self._ensure_open()
        return None

    def close(self) -> None:
        if self._closed:
            return
        closer = getattr(self._client, "close", None)
        if callable(closer):
            closer()
        self._closed = True
        self._client = None
