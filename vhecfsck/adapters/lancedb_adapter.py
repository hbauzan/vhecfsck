"""LanceDB read-only IndexAdapter implementation (P5)."""

from __future__ import annotations

import contextlib
import importlib
import warnings
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
from numpy.typing import NDArray

from vhecfsck.adapters.base import IdArray, IndexAdapter, SearchParams
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

FloatMatrix = NDArray[np.float32]

SUPPORTED_LANCE_MIN = (0, 11, 0)
SUPPORTED_LANCE_MAX = (12, 0, 0)
SUPPORTED_LANCEDB_MIN = (0, 37, 1)
SUPPORTED_LANCEDB_MAX = (1, 0, 0)

_VERSION_WARNING_EMITTED = False


def _parse_version_tuple(ver_str: str) -> tuple[int, ...]:
    clean = ver_str.split("-")[0].split("+")[0].split(".dev")[0]
    parts: list[int] = []
    for p in clean.split("."):
        if p.isdigit():
            parts.append(int(p))
        else:
            break
    return tuple(parts)


def check_lancedb_version_compatibility(lance_ver: str, lancedb_ver: str) -> str | None:
    """Check if runtime lance and lancedb versions are within tested range."""
    l_tuple = _parse_version_tuple(lance_ver)
    ldb_tuple = _parse_version_tuple(lancedb_ver)

    if l_tuple and (l_tuple < SUPPORTED_LANCE_MIN or l_tuple >= SUPPORTED_LANCE_MAX):
        return (
            f"Lance version '{lance_ver}' is outside tested range (>=0.11.0, <12.0.0)"
        )
    if ldb_tuple and (
        ldb_tuple < SUPPORTED_LANCEDB_MIN or ldb_tuple >= SUPPORTED_LANCEDB_MAX
    ):
        return (
            f"LanceDB version '{lancedb_ver}' is outside tested range "
            f"(>=0.37.1, <1.0.0)"
        )
    return None


class LanceDBAdapter(IndexAdapter):
    """Read-only window onto a Lance / LanceDB dataset."""

    def __init__(
        self,
        target: str,
        *,
        column: str | None = None,
        dataset_version: int | None = None,
    ) -> None:
        """Open a Lance dataset read-only.

        Args:
            target: Path to dataset/table or lance:// URI.
            column: Optional explicit vector column name.
            dataset_version: Optional version/snapshot integer to pin.

        Raises:
            UsageError: If lancedb/pylance extra is missing or dataset is invalid.
        """
        global _VERSION_WARNING_EMITTED
        try:
            lance = importlib.import_module("lance")
            lancedb = importlib.import_module("lancedb")
        except ImportError as exc:
            safe = redact_secrets(target)
            raise UsageError(
                f"LanceDB support is not installed (target={safe})",
                hint='pip install "vhecfsck[lancedb]"',
            ) from exc

        if not _VERSION_WARNING_EMITTED:
            l_ver = str(getattr(lance, "__version__", "0.0.0"))
            ldb_ver = str(getattr(lancedb, "__version__", "0.0.0"))
            warn_msg = check_lancedb_version_compatibility(l_ver, ldb_ver)
            if warn_msg:
                warnings.warn(warn_msg, UserWarning, stacklevel=2)
            _VERSION_WARNING_EMITTED = True

        # Parse query params if present in URI
        raw_target = target
        if "://" in target or "?" in target:
            parsed = urlparse(target if "://" in target else f"lance://{target}")
            qs = parse_qs(parsed.query)
            if column is None and "column" in qs:
                column = qs["column"][0]
            if dataset_version is None:
                ver_str = qs.get("dataset_version", qs.get("version", [None]))[0]
                if ver_str is not None:
                    with contextlib.suppress(ValueError):
                        dataset_version = int(ver_str)
            if parsed.scheme == "lance":
                raw_target = parsed.path or parsed.netloc

        resolved_path = self._resolve_dataset_path(raw_target)

        try:
            ds = lance.dataset(resolved_path, version=dataset_version)
        except Exception as exc:
            safe = redact_secrets(target)
            msg = (
                f"Failed to open Lance dataset version {dataset_version} at {safe}: "
                f"{redact_secrets(str(exc))}"
            )
            raise UsageError(
                msg,
                hint="Verify dataset path and --dataset-version N",
            ) from exc

        self._ds: Any = ds
        self._target_location = str(target)
        self._pinned_version = int(ds.version)
        self._lance_module = lance

        # Resolve vector column
        self._vector_col = self._detect_vector_column(column)

        # Detect dimensionality
        field = ds.schema.field(self._vector_col)
        field_type = field.type
        if hasattr(field_type, "list_size"):
            self._dimension_val = int(field_type.list_size)
        else:
            msg = f"Vector column {self._vector_col} must be fixed_size_list"
            raise UsageError(msg)

        # Index metadata discovery
        (
            self._index_name_val,
            self._index_kind_val,
            self._metric_space_val,
            self._index_stats_data,
        ) = self._introspect_index()

        has_partitions = self._index_kind_val in (
            IndexKind.IVF,
            IndexKind.IVF_PQ,
        )
        self._capabilities_val = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=True,
            deleted_counts_exact=True,
            report_partitions=has_partitions,
            partition_live_counts=has_partitions,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=False,
        )

    def _resolve_dataset_path(self, raw_path: str) -> str:
        p = Path(raw_path)
        if p.is_dir():
            if (p / "data.lance").exists():
                return str(p / "data.lance")
            if p.suffix == ".lance":
                return str(p)
            for child in p.glob("*.lance"):
                if child.is_dir():
                    return str(child)
        return raw_path

    def _detect_vector_column(self, user_col: str | None) -> str:
        schema = self._ds.schema
        candidates: list[str] = []
        for name in schema.names:
            field = schema.field(name)
            t = field.type
            if hasattr(t, "list_size") and hasattr(t, "value_type"):
                val_t_str = str(t.value_type)
                if any(
                    k in val_t_str
                    for k in ("float", "double", "halffloat", "float16", "float32")
                ):
                    candidates.append(name)

        if user_col is not None:
            if user_col not in schema.names:
                msg = (
                    f"Specified vector column '{user_col}' not found in dataset schema"
                )
                raise UsageError(msg, hint=f"Available columns: {schema.names}")
            return user_col

        if not candidates:
            msg = f"No vector column found in dataset schema ({schema.names})"
            raise UsageError(msg)

        if len(candidates) > 1:
            msg = (
                f"Multiple vector columns found: {candidates}. Please specify --column."
            )
            raise UsageError(msg, hint=f"Pass --column {candidates[0]}")

        return candidates[0]

    def _introspect_index(
        self,
    ) -> tuple[str, IndexKind, MetricSpace, dict[str, Any] | None]:
        desc_indices = self._ds.describe_indices()
        matching = [
            idx
            for idx in desc_indices
            if hasattr(idx, "field_names") and self._vector_col in idx.field_names
        ]
        if not matching:
            return "default", IndexKind.FLAT, MetricSpace.L2, None

        idx_info = matching[0]
        idx_name = str(getattr(idx_info, "name", "vector_idx"))

        stats_data: dict[str, Any] | None = None
        kind = IndexKind.FLAT
        metric = MetricSpace.L2

        try:
            if hasattr(self._ds, "stats") and hasattr(self._ds.stats, "index_stats"):
                stats_data = self._ds.stats.index_stats(idx_name)
            else:
                stats_data = self._ds.index_statistics(idx_name)

            if stats_data and isinstance(stats_data, dict):
                sub_indices = stats_data.get("indices", [])
                if sub_indices and isinstance(sub_indices, list):
                    first_sub = sub_indices[0]
                    if isinstance(first_sub, dict):
                        idx_type_str = str(
                            first_sub.get(
                                "index_type",
                                stats_data.get("index_type", ""),
                            )
                        ).upper()
                        if "IVF_PQ" in idx_type_str or "PQ" in idx_type_str:
                            kind = IndexKind.IVF_PQ
                        elif "IVF" in idx_type_str:
                            kind = IndexKind.IVF
                        elif "HNSW" in idx_type_str:
                            kind = IndexKind.HNSW
                        else:
                            kind = IndexKind.FLAT

                        m_str = str(first_sub.get("metric_type", "l2")).lower()
                        if "cosine" in m_str:
                            metric = MetricSpace.COSINE
                        elif "dot" in m_str or "ip" in m_str:
                            metric = MetricSpace.DOT
                        else:
                            metric = MetricSpace.L2
        except Exception:
            pass

        return idx_name, kind, metric, stats_data

    @property
    def descriptor(self) -> TargetDescriptor:
        """Engine name, version, index kind, redacted target location."""
        return TargetDescriptor(
            engine="lancedb",
            engine_version=str(getattr(self._lance_module, "__version__", "11.0.0")),
            index_kind=self._index_kind_val,
            index_name=self._index_name_val,
            location=redact_secrets(self._target_location),
            dimension=self._dimension_val,
            metric_space=self._metric_space_val,
        )

    @property
    def capabilities(self) -> Capabilities:
        """Which optional reads this engine supports."""
        return self._capabilities_val

    @property
    def dimension(self) -> int:
        """Embedding dimensionality of target index."""
        return self._dimension_val

    @property
    def metric_space(self) -> MetricSpace:
        """COSINE | L2 | DOT."""
        return self._metric_space_val

    def counts(self) -> IndexCounts:
        """Live / deleted / total / indexed counts from Lance fragments."""
        frags = self._ds.get_fragments()
        physical = sum(int(f.physical_rows) for f in frags)
        deleted = sum(int(f.num_deletions) for f in frags)
        live = physical - deleted

        indexed = live
        if self._index_stats_data and isinstance(self._index_stats_data, dict):
            indexed = int(self._index_stats_data.get("num_indexed_rows", live))

        return IndexCounts(
            live=live,
            deleted=deleted,
            total=physical,
            indexed=indexed,
            degenerate=0,
            exact=True,
            read_at=datetime.now(UTC),
        )

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        """Stream live vectors with stable int64 IDs (_rowid)."""
        scanner = self._ds.scanner(
            columns=["_rowid", self._vector_col],
            batch_size=batch_size,
        )
        for batch in scanner.to_batches():
            ids = np.array(
                batch["_rowid"].to_numpy(zero_copy_only=False), dtype=np.int64
            )
            vec_list = batch[self._vector_col].to_pylist()
            vec_2d = np.ascontiguousarray(
                np.array(vec_list, dtype=np.float32).reshape(-1, self._dimension_val)
            )
            yield VectorBatch(ids=ids, vectors=vec_2d)

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        """Deterministic live-ID sample."""
        scanner = self._ds.scanner(columns=["_rowid"])
        all_chunks = [
            b["_rowid"].to_numpy(zero_copy_only=False) for b in scanner.to_batches()
        ]
        if not all_chunks:
            return np.empty(0, dtype=np.int64)
        all_ids = np.concatenate(all_chunks).astype(np.int64)
        if len(all_ids) <= n:
            return all_ids
        rng = np.random.default_rng(seed)
        sampled = rng.choice(all_ids, size=n, replace=False)
        return np.ascontiguousarray(sampled, dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        """Random access by ID (take)."""
        tbl = self._ds.take(ids.tolist(), columns=[self._vector_col])
        vec_list = tbl[self._vector_col].to_pylist()
        vec_2d = np.ascontiguousarray(
            np.array(vec_list, dtype=np.float32).reshape(-1, self._dimension_val)
        )
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=vec_2d,
        )

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        """Native k-NN search via Lance dataset to_table."""
        nprobe = params.get("nprobe", 10)
        refine_factor = int(params.get("refine_factor", 1))

        nearest_dict: dict[str, Any] = {
            "column": self._vector_col,
            "q": queries,
            "k": k,
            "nprobes": nprobe,
            "refine_factor": refine_factor,
        }

        res_table = self._ds.to_table(nearest=nearest_dict)

        num_queries = len(queries)
        out_ids = np.full((num_queries, k), -1, dtype=np.int64)
        out_dists = np.full((num_queries, k), np.nan, dtype=np.float32)

        q_idx_col = res_table["query_index"].to_numpy()
        id_col_name = "_rowid" if "_rowid" in res_table.column_names else "id"
        res_ids = res_table[id_col_name].to_numpy()
        res_dists = res_table["_distance"].to_numpy()

        counts_per_q: dict[int, int] = {}
        for q_idx, row_id, dist in zip(q_idx_col, res_ids, res_dists, strict=False):
            q_i = int(q_idx)
            pos = counts_per_q.get(q_i, 0)
            if pos < k:
                out_ids[q_i, pos] = int(row_id)
                out_dists[q_i, pos] = float(dist)
                counts_per_q[q_i] = pos + 1

        return SearchResult(
            ids=out_ids,
            distances=out_dists,
            effective_params={"nprobe": nprobe, "refine_factor": refine_factor},
        )

    def partitions(self) -> PartitionStats | None:
        """IVF cell row counts from index statistics."""
        if not self.capabilities.report_partitions or not self._index_stats_data:
            return None

        indices = self._index_stats_data.get("indices", [])
        if not indices or not isinstance(indices, list):
            return None

        first_sub = indices[0]
        if not isinstance(first_sub, dict):
            return None

        part_list = first_sub.get("partitions", [])
        if not part_list or len(part_list) <= 1:
            return None

        counts = np.array([int(p.get("size", 0)) for p in part_list], dtype=np.int64)

        return PartitionStats(
            sizes=counts,
            includes_deleted=True,
            n_partitions=len(counts),
        )

    def graph_stats(self) -> GraphStats | None:
        """Graph stats unavailable for LanceDB."""
        return None

    def close(self) -> None:
        """Release reference to dataset."""
        self._ds = None
