#!/usr/bin/env python3
# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P8-01 reference-dataset calibration harness.

Runs the metric suite over Gaussian controls, named synthetic pathologies,
and (optionally) public ANN corpora. Writes derived statistics only —
never redistributes source vectors (risk R13).

Regenerate committed artefacts:

    uv run python scripts/calibrate.py --profile reference --out docs/calibration
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.random import default_rng
from numpy.typing import NDArray
from vhecfsck.adapters.base import (
    FloatMatrix,
    IdArray,
    IndexAdapter,
    SearchParams,
    iter_vector_batches,
)
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.adapters.synthetic_adapter import SyntheticAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.core.canary import CANARY_METRIC_ID
from vhecfsck.core.fragmentation import DFI_METRIC_ID
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.hubness import ANTIHUB_METRIC_ID, HUB_SHARE_METRIC_ID
from vhecfsck.core.partitions import PARTITION_CV_METRIC_ID
from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets
from vhecfsck.models import (
    Capabilities,
    IndexCounts,
    IndexKind,
    MetricResult,
    MetricSpace,
    MetricState,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)
from vhecfsck.models.report import metric_by_id
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import (
    apply_churn,
    corpus_state_from_generated,
    inject_antihubs,
    inject_hubs,
)
from vhecfsck.synthetic.scenarios import ScenarioSize

FIVE_METRICS: frozenset[str] = frozenset(
    {
        CANARY_METRIC_ID,
        HUB_SHARE_METRIC_ID,
        ANTIHUB_METRIC_ID,
        DFI_METRIC_ID,
        PARTITION_CV_METRIC_ID,
    }
)

CSV_COLUMNS: tuple[str, ...] = (
    "kind",
    "family",
    "dataset_id",
    "n",
    "dimension",
    "metric_space",
    "index_kind",
    "hubness_sample_size",
    "k_hub",
    "k",
    "queries",
    "n_lists",
    "metric_id",
    "state",
    "value",
    "unavailable_reason",
    "evidence_strength",
    "verdict",
    "seed",
    "profile",
)

SENSITIVITY_COLUMNS: tuple[str, ...] = (
    "family",
    "dataset_id",
    "n",
    "dimension",
    "hubness_sample_size",
    "k_hub",
    "hub_share_top1pct",
    "hub_share_state",
    "hub_share_reason",
    "antihub_fraction",
    "antihub_state",
    "antihub_reason",
    "seed",
    "profile",
)

SKIPPED_COLUMNS: tuple[str, ...] = ("dataset_id", "family", "reason")

GAUSSIAN_DIMS_REFERENCE: tuple[int, ...] = (64, 128, 384, 768, 1536)
KMEANS_ITERS = 12
_KMEANS_SEED_OFFSET = 4_009
_SCENARIO_SIZES: dict[str, ScenarioSize] = {
    "tiny": "tiny",
    "small": "small",
    "large": "large",
}


class DatasetSkippedError(Exception):
    """Public corpus was not loaded; never substitute a metric value."""

    def __init__(self, dataset_id: str, reason: str) -> None:
        super().__init__(f"{dataset_id}: {reason}")
        self.dataset_id = dataset_id
        self.reason = reason


@dataclass(frozen=True)
class DatasetSpec:
    """Licence + provenance record for one calibration corpus."""

    id: str
    family: str
    title: str
    licence: str
    spdx: str
    provenance: str
    status: str
    notes: str = ""
    metric_space: str = "L2"
    urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Profile:
    """Named run shape. Smoke is the default-suite contract; reference is published."""

    name: str
    n: int
    gaussian_dims: tuple[int, ...]
    hubness_sample_sizes: tuple[int, ...]
    k_hubs: tuple[int, ...]
    synthetic_names: tuple[str, ...]
    synthetic_size: str
    include_public: bool
    public_ids: tuple[str, ...]
    queries: int
    k: int
    seed: int
    baseline_hubness_sample_size: int
    baseline_k_hub: int
    allow_download: bool = False


@dataclass(frozen=True)
class RunArtefacts:
    """Paths written by one ``run_profile`` invocation."""

    results_csv: Path
    sensitivity_csv: Path
    skipped_csv: Path
    datasets_md: Path


PROFILE_SMOKE = Profile(
    name="smoke",
    n=1_200,
    gaussian_dims=(16,),
    hubness_sample_sizes=(1_000,),
    k_hubs=(5, 10),
    synthetic_names=("hubby", "tombstoned"),
    synthetic_size="smoke",
    include_public=False,
    public_ids=(),
    queries=16,
    k=10,
    seed=1337,
    baseline_hubness_sample_size=1_000,
    baseline_k_hub=5,
    allow_download=False,
)

PROFILE_REFERENCE = Profile(
    name="reference",
    n=20_000,
    gaussian_dims=GAUSSIAN_DIMS_REFERENCE,
    hubness_sample_sizes=(1_000, 5_000, 20_000, 50_000),
    k_hubs=(5, 10, 20),
    synthetic_names=("healthy", "drifted", "tombstoned", "hubby"),
    synthetic_size="small",
    include_public=True,
    public_ids=("sift-128", "gist-960", "glove-100", "sentence-minilm"),
    queries=200,
    k=10,
    seed=1337,
    baseline_hubness_sample_size=20_000,
    baseline_k_hub=10,
    allow_download=True,
)


def _gaussian_specs() -> tuple[DatasetSpec, ...]:
    rows: list[DatasetSpec] = []
    for dim in GAUSSIAN_DIMS_REFERENCE:
        rows.append(
            DatasetSpec(
                id=f"gaussian-{dim}",
                family="gaussian",
                title=f"Isotropic Gaussian N(0, I), d={dim}",
                licence="Generated in-process; no third-party corpus.",
                spdx="LicenseRef-Generated",
                provenance=(
                    "numpy Generator.standard_normal, seed from the calibration "
                    "profile. Theoretical hubness control (ADR-0006 / P8-01)."
                ),
                status="generated",
            )
        )
    return tuple(rows)


_SYNTHETIC_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        id="synthetic-healthy",
        family="synthetic",
        title="Named scenario healthy (balanced IVF)",
        licence="Generated in-process (vhecfsck synthetic).",
        spdx="LicenseRef-Generated",
        provenance="vhecfsck.synthetic.scenarios.scenario_healthy",
        status="generated",
        notes="Positive control for a healthy IVF build.",
    ),
    DatasetSpec(
        id="synthetic-drifted",
        family="synthetic",
        title="Named scenario drifted (append without centroid refit)",
        licence="Generated in-process (vhecfsck synthetic).",
        spdx="LicenseRef-Generated",
        provenance="vhecfsck.synthetic.scenarios.scenario_drifted (lance#4164 analogue)",
        status="generated",
    ),
    DatasetSpec(
        id="synthetic-tombstoned",
        family="synthetic",
        title="Named scenario tombstoned (path-blocking deletes)",
        licence="Generated in-process (vhecfsck synthetic).",
        spdx="LicenseRef-Generated",
        provenance="vhecfsck.synthetic.scenarios.scenario_tombstoned (pgvector#244 analogue)",
        status="generated",
    ),
    DatasetSpec(
        id="synthetic-hubby",
        family="synthetic",
        title="Named scenario hubby (injected hubs + anti-hubs)",
        licence="Generated in-process (vhecfsck synthetic).",
        spdx="LicenseRef-Generated",
        provenance="vhecfsck.synthetic.scenarios.scenario_hubby",
        status="generated",
    ),
)

_PUBLIC_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        id="sift-128",
        family="public",
        title="ANN_SIFT1M base descriptors (prefix subsample)",
        licence=(
            "TEXMEX / INRIA: Laurent Amsaleg and Hervé Jégou waived copyright "
            "to the extent possible under law (CC0-like waiver published from France). "
            "Cite Jegou, Douze, Schmid, IEEE TPAMI 2011."
        ),
        spdx="CC0-1.0",
        provenance="http://corpus-texmex.irisa.fr/ — ANN_SIFT1M sift.tar.gz, sift_base.fvecs",
        status="download",
        urls=(
            "http://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz",
            "ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz",
        ),
        notes="Prefix of N vectors from the official base split; vectors are not committed.",
    ),
    DatasetSpec(
        id="gist-960",
        family="public",
        title="ANN_GIST1M base descriptors (prefix subsample)",
        licence=(
            "Same TEXMEX waiver as SIFT1M. Cite Jegou, Douze, Schmid, IEEE TPAMI 2011."
        ),
        spdx="CC0-1.0",
        provenance="http://corpus-texmex.irisa.fr/ — ANN_GIST1M gist.tar.gz, gist_base.fvecs",
        status="download",
        urls=(
            "http://ftp.irisa.fr/local/texmex/corpus/gist.tar.gz",
            "ftp://ftp.irisa.fr/local/texmex/corpus/gist.tar.gz",
        ),
        notes="Archive is ~2.6 GB; stream the prefix then stop. Vectors are not committed.",
    ),
    DatasetSpec(
        id="glove-100",
        family="public",
        title="GloVe 6B 100-d (prefix of most-frequent tokens)",
        licence="Pre-trained vectors: Open Data Commons PDDL 1.0.",
        spdx="PDDL-1.0",
        provenance="https://nlp.stanford.edu/projects/glove/ — glove.6B.zip / glove.6B.100d.txt",
        status="download",
        metric_space="COSINE",
        urls=("https://nlp.stanford.edu/data/glove.6B.zip",),
        notes="Prefix of N rows (highest-frequency tokens). Rows are L2-normalised.",
    ),
    DatasetSpec(
        id="nytimes-256",
        family="public",
        title="ann-benchmarks nytimes-256-angular",
        licence=(
            "Derived from The New York Times Annotated Corpus (LDC2008T19). "
            "LDC terms forbid redistribution and restrict use to non-commercial "
            "linguistic research. Not used in published calibration (R13)."
        ),
        spdx="LicenseRef-LDC-NYT",
        provenance="https://catalog.ldc.upenn.edu/LDC2008T19 via ann-benchmarks nytimes-256-angular",
        status="excluded",
        metric_space="COSINE",
        notes="Excluded. Do not download or cache this corpus in the harness.",
    ),
    DatasetSpec(
        id="sentence-minilm",
        family="public",
        title="Modern sentence embeddings (operator-supplied float32 npy)",
        licence=(
            "Operator must record the corpus and model licences in a sidecar. "
            "all-MiniLM-L6-v2 weights are Apache-2.0; Wikipedia-derived text is CC BY-SA."
        ),
        spdx="Apache-2.0",
        provenance=(
            "Cache file sentence-minilm.npy (shape (n, d) float32). No default "
            "host: a 35M-row Wikipedia MiniLM dump is tens of GB and is not fetched."
        ),
        status="cache_only",
        metric_space="COSINE",
        notes="Drop a permissively licensed npy into the cache to include this row.",
    ),
)

CATALOG: tuple[DatasetSpec, ...] = _gaussian_specs() + _SYNTHETIC_SPECS + _PUBLIC_SPECS

_CATALOG_BY_ID: dict[str, DatasetSpec] = {spec.id: spec for spec in CATALOG}


@dataclass
class _PreparedCorpus:
    dataset_id: str
    family: str
    adapter: IndexAdapter
    search_params: SearchParams
    n_lists: int


class CalibrationAdapter:
    """In-memory exact-search adapter with BLAS k-means partition sizes.

    Search delegates to blocked ``exact_knn`` so a live, undeleted corpus
    scores canary recall ``1.0`` (healthy exact index). Partition CV uses
    BLAS k-means list sizes, not SyntheticAdapter's pure-Python k-means
    (lesson 25).
    """

    def __init__(
        self,
        vectors: NDArray[np.float32],
        *,
        metric_space: MetricSpace,
        dataset_id: str,
        seed: int,
        n_lists: int,
        kmeans_iters: int = KMEANS_ITERS,
    ) -> None:
        self._closed = False
        self._vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        n = int(self._vectors.shape[0])
        d = int(self._vectors.shape[1]) if n else 0
        self._ids = np.arange(n, dtype=np.int64)
        self._metric = metric_space
        self._id_to_row = {int(i): i for i in range(n)}
        self._n_lists = max(1, min(int(n_lists), n)) if n else 0
        if n and self._n_lists:
            self._assignment = _blas_kmeans(
                self._vectors,
                self._n_lists,
                seed=seed + _KMEANS_SEED_OFFSET,
                iters=kmeans_iters,
                metric=metric_space,
            )
        else:
            self._assignment = np.zeros(n, dtype=np.int64)
        loc = redact_secrets(f"calibration://{dataset_id}")
        self._descriptor = TargetDescriptor(
            engine="calibration",
            engine_version="0.1.0",
            index_kind=IndexKind.IVF if self._n_lists else IndexKind.FLAT,
            index_name=dataset_id,
            location=loc,
            dimension=d,
            metric_space=metric_space,
        )
        self._capabilities = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=True,
            deleted_counts_exact=True,
            report_partitions=self._n_lists > 0,
            partition_live_counts=self._n_lists > 0,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=False,
        )

    @property
    def descriptor(self) -> TargetDescriptor:
        self._ensure_open()
        return self._descriptor

    @property
    def capabilities(self) -> Capabilities:
        self._ensure_open()
        return self._capabilities

    @property
    def dimension(self) -> int:
        self._ensure_open()
        return self._descriptor.dimension

    @property
    def metric_space(self) -> MetricSpace:
        self._ensure_open()
        return self._metric

    def counts(self) -> IndexCounts:
        self._ensure_open()
        n = int(self._ids.shape[0])
        return IndexCounts(
            live=n,
            deleted=0,
            total=n,
            indexed=n,
            degenerate=0,
            exact=True,
            read_at=datetime.now(tz=UTC),
        )

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        self._ensure_open()
        return iter_vector_batches(self._ids, self._vectors, batch_size=batch_size)

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        self._ensure_open()
        take = min(int(n), int(self._ids.shape[0]))
        if take == 0:
            return np.empty(0, dtype=np.int64)
        rng = default_rng(seed)
        order = rng.choice(self._ids.shape[0], size=take, replace=False)
        return np.ascontiguousarray(self._ids[order], dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        self._ensure_open()
        rows = np.empty(ids.shape[0], dtype=np.int64)
        for i in range(ids.shape[0]):
            key = int(ids[i])
            row = self._id_to_row.get(key)
            if row is None:
                msg = f"unknown vector id: {key}"
                raise UsageError(msg, hint="sample ids from this adapter")
            rows[i] = row
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=np.ascontiguousarray(self._vectors[rows], dtype=np.float32),
        )

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        del params
        self._ensure_open()
        take = max(int(k), 1)
        knn = exact_knn(
            [VectorBatch(ids=self._ids, vectors=self._vectors)],
            queries,
            take,
            self._metric,
            working_set_mb=256.0,
            n_total=int(self._ids.shape[0]),
        )
        return SearchResult(
            ids=knn.ids,
            distances=knn.distances,
            effective_params={"exact": True},
        )

    def partitions(self) -> PartitionStats | None:
        self._ensure_open()
        if self._n_lists < 1:
            return None
        sizes = np.zeros(self._n_lists, dtype=np.int64)
        for cell in self._assignment.tolist():
            ci = int(cell)
            if 0 <= ci < self._n_lists:
                sizes[ci] = sizes[ci] + np.int64(1)
        return PartitionStats(
            sizes=sizes,
            includes_deleted=False,
            n_partitions=self._n_lists,
        )

    def graph_stats(self) -> None:
        self._ensure_open()
        return None

    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            msg = "CalibrationAdapter is closed"
            raise RuntimeError(msg)


def _search_params_from_spec(raw: Mapping[str, object]) -> SearchParams:
    params: SearchParams = {}
    nprobe = raw.get("nprobe")
    if isinstance(nprobe, int):
        params["nprobe"] = nprobe
    ef_search = raw.get("ef_search")
    if isinstance(ef_search, int):
        params["ef_search"] = ef_search
    refine = raw.get("refine_factor")
    if isinstance(refine, float):
        params["refine_factor"] = refine
    exact = raw.get("exact")
    if isinstance(exact, bool):
        params["exact"] = exact
    return params


def _n_lists_for(n: int) -> int:
    if n < 1:
        return 0
    return max(4, round(n**0.5))


def _l2_normalize_rows(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe = np.maximum(norms, np.float32(1e-12))
    return np.ascontiguousarray(vectors / safe, dtype=np.float32)


def _blas_kmeans(
    vectors: NDArray[np.float32],
    n_lists: int,
    *,
    seed: int,
    iters: int,
    metric: MetricSpace,
) -> NDArray[np.int64]:
    n = int(vectors.shape[0])
    k = min(int(n_lists), n)
    rng = default_rng(seed)
    init = rng.choice(n, size=k, replace=False)
    centroids = np.array(vectors[init], dtype=np.float32, copy=True)
    if metric is MetricSpace.COSINE:
        centroids = _l2_normalize_rows(centroids)
    x2 = np.sum(vectors * vectors, axis=1, keepdims=True)
    assignment = np.zeros(n, dtype=np.int64)
    for _ in range(max(1, iters)):
        dots = vectors @ centroids.T
        if metric is MetricSpace.L2:
            c2 = np.sum(centroids * centroids, axis=1, keepdims=True).T
            dist = x2 + c2 - (np.float32(2.0) * dots)
        elif metric is MetricSpace.COSINE:
            dist = np.float32(1.0) - dots
        else:
            dist = -dots
        assignment = np.argmin(dist, axis=1).astype(np.int64, copy=False)
        new_c = np.zeros_like(centroids)
        for cell in range(k):
            mask = assignment == cell
            count = int(np.sum(mask))
            if count > 0:
                new_c[cell] = np.mean(vectors[mask], axis=0)
            else:
                new_c[cell] = centroids[cell]
        if metric is MetricSpace.COSINE:
            new_c = _l2_normalize_rows(new_c)
        centroids = new_c
    return assignment


def read_fvecs(path: Path, *, max_vectors: int | None = None) -> NDArray[np.float32]:
    """Read a TEXMEX ``.fvecs`` file (little-endian dim header + float32 body)."""
    with path.open("rb") as fh:
        return _read_fvecs_stream(fh, max_vectors=max_vectors)


def write_fvecs(path: Path, vectors: NDArray[np.float32]) -> None:
    """Write a TEXMEX ``.fvecs`` file (test helper; not used on audited targets)."""
    arr = np.ascontiguousarray(vectors, dtype=np.float32)
    with path.open("wb") as fh:
        for row in arr:
            fh.write(struct.pack("<i", int(row.shape[0])))
            fh.write(np.ascontiguousarray(row, dtype="<f4").tobytes())


def _read_fvecs_stream(
    fh: BinaryIO,
    *,
    max_vectors: int | None = None,
) -> NDArray[np.float32]:
    rows: list[NDArray[np.float32]] = []
    while max_vectors is None or len(rows) < max_vectors:
        header = fh.read(4)
        if not header or len(header) < 4:
            break
        dim = struct.unpack("<i", header)[0]
        if dim < 1 or dim > 16_384:
            msg = f"implausible fvecs dimension: {dim}"
            raise ValueError(msg)
        body = fh.read(dim * 4)
        if body is None or len(body) < dim * 4:
            break
        rows.append(np.frombuffer(body, dtype="<f4").astype(np.float32, copy=True))
    if not rows:
        return np.zeros((0, 0), dtype=np.float32)
    return np.ascontiguousarray(np.stack(rows, axis=0), dtype=np.float32)


def parse_glove_lines(
    lines: Iterable[str],
    *,
    max_vectors: int,
) -> tuple[NDArray[np.float32], tuple[str, ...]]:
    """Parse GloVe text format; keep the first ``max_vectors`` rows."""
    vecs: list[list[float]] = []
    tokens: list[str] = []
    dim: int | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        token = parts[0]
        nums = [float(x) for x in parts[1:]]
        if dim is None:
            dim = len(nums)
        if len(nums) != dim:
            continue
        tokens.append(token)
        vecs.append(nums)
        if len(vecs) >= max_vectors:
            break
    if not vecs:
        return np.zeros((0, 0), dtype=np.float32), ()
    return np.ascontiguousarray(np.asarray(vecs, dtype=np.float32)), tuple(tokens)


def _cache_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return Path.home() / ".cache" / "vhecfsck" / "calibration"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "vhecfsck-calibration/0.1"},
    )
    with urllib.request.urlopen(request, timeout=120) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def _ensure_archive(
    spec: DatasetSpec,
    cache: Path,
    *,
    allow_download: bool,
    filename: str,
) -> Path:
    dest = cache / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    if not allow_download:
        raise DatasetSkippedError(
            spec.id, f"{filename} not in cache; download disabled"
        )
    last_err = "no urls"
    for url in spec.urls:
        try:
            _download(url, dest)
            return dest
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_err = str(exc)
    raise DatasetSkippedError(spec.id, f"download failed: {last_err}")


def _load_sift(
    spec: DatasetSpec, cache: Path, n: int, allow_download: bool
) -> NDArray[np.float32]:
    archive = _ensure_archive(
        spec, cache, allow_download=allow_download, filename="sift.tar.gz"
    )
    with tarfile.open(archive, "r:gz") as tar:
        try:
            member = _first_member(tar, ("sift_base.fvecs", "sift/sift_base.fvecs"))
        except FileNotFoundError as exc:
            raise DatasetSkippedError(spec.id, str(exc)) from exc
        extracted = tar.extractfile(member)
        if extracted is None:
            raise DatasetSkippedError(spec.id, "sift_base.fvecs missing from archive")
        with extracted:
            return _read_fvecs_stream(extracted, max_vectors=n)


def _load_gist(
    spec: DatasetSpec, cache: Path, n: int, allow_download: bool
) -> NDArray[np.float32]:
    archive = _ensure_archive(
        spec, cache, allow_download=allow_download, filename="gist.tar.gz"
    )
    with tarfile.open(archive, "r:gz") as tar:
        try:
            member = _first_member(tar, ("gist_base.fvecs", "gist/gist_base.fvecs"))
        except FileNotFoundError as exc:
            raise DatasetSkippedError(spec.id, str(exc)) from exc
        extracted = tar.extractfile(member)
        if extracted is None:
            raise DatasetSkippedError(spec.id, "gist_base.fvecs missing from archive")
        with extracted:
            return _read_fvecs_stream(extracted, max_vectors=n)


def _load_glove(
    spec: DatasetSpec, cache: Path, n: int, allow_download: bool
) -> NDArray[np.float32]:
    archive = _ensure_archive(
        spec, cache, allow_download=allow_download, filename="glove.6B.zip"
    )
    with zipfile.ZipFile(archive) as zf:
        name = "glove.6B.100d.txt"
        if name not in zf.namelist():
            matches = [
                item for item in zf.namelist() if item.endswith("glove.6B.100d.txt")
            ]
            if not matches:
                raise DatasetSkippedError(spec.id, "glove.6B.100d.txt missing from zip")
            name = matches[0]
        with zf.open(name) as raw:
            text = raw.read().decode("utf-8", errors="replace").splitlines()
    vectors, _tokens = parse_glove_lines(text, max_vectors=n)
    if vectors.shape[0] == 0:
        raise DatasetSkippedError(spec.id, "glove file parsed to zero rows")
    return _l2_normalize_rows(vectors)


def _load_sentence_npy(spec: DatasetSpec, cache: Path, n: int) -> NDArray[np.float32]:
    path = cache / "sentence-minilm.npy"
    if not path.is_file():
        raise DatasetSkippedError(spec.id, "sentence-minilm.npy not in cache")
    loaded = np.load(path)
    arr = np.ascontiguousarray(loaded, dtype=np.float32)
    if arr.ndim != 2:
        raise DatasetSkippedError(spec.id, "sentence-minilm.npy must be rank-2")
    if arr.shape[0] > n:
        arr = arr[:n]
    return _l2_normalize_rows(arr)


def _first_member(tar: tarfile.TarFile, names: Sequence[str]) -> tarfile.TarInfo:
    by_name = {member.name: member for member in tar.getmembers() if member.isfile()}
    for name in names:
        if name in by_name:
            return by_name[name]
    for member in tar.getmembers():
        if member.isfile() and member.name.endswith("base.fvecs"):
            return member
    msg = f"no matching fvecs member (looked for {', '.join(names)})"
    raise FileNotFoundError(msg)


def _gaussian_vectors(n: int, dim: int, seed: int) -> NDArray[np.float32]:
    rng = default_rng(seed)
    return np.ascontiguousarray(rng.standard_normal((n, dim)), dtype=np.float32)


def _calibration_adapter(
    dataset_id: str,
    vectors: NDArray[np.float32],
    *,
    metric_space: MetricSpace,
    seed: int,
) -> CalibrationAdapter:
    n = int(vectors.shape[0])
    return CalibrationAdapter(
        vectors,
        metric_space=metric_space,
        dataset_id=dataset_id,
        seed=seed,
        n_lists=_n_lists_for(n),
    )


def _smoke_synthetic(name: str, seed: int) -> _PreparedCorpus:
    if name == "hubby":
        gen = generate_corpus(
            1_200,
            64,
            n_clusters=8,
            cluster_std=0.1,
            cluster_size_skew=0.0,
            seed=seed + 40,
            metric_space=MetricSpace.L2,
        )
        state = corpus_state_from_generated(gen)
        state = inject_hubs(state, n_hubs=6, strength=4.0, seed=seed + 41)
        state = inject_antihubs(
            state, n_antihubs=12, distance_factor=8.0, seed=seed + 42
        )
        adapter = SyntheticAdapter(
            state,
            mode="exact",
            index_name="synthetic-hubby",
            location=redact_secrets("calibration://synthetic-hubby"),
        )
        return _PreparedCorpus(
            dataset_id="synthetic-hubby",
            family="synthetic",
            adapter=adapter,
            search_params={"exact": True},
            n_lists=0,
        )
    if name == "tombstoned":
        gen = generate_corpus(
            1_200,
            16,
            n_clusters=8,
            cluster_std=0.2,
            cluster_size_skew=0.5,
            seed=seed + 50,
            metric_space=MetricSpace.L2,
        )
        state = apply_churn(
            corpus_state_from_generated(gen),
            delete_fraction=0.35,
            skew=2.0,
            seed=seed + 51,
        )
        adapter = SyntheticAdapter(
            state,
            mode="ivf_tombstoned",
            n_lists=8,
            build_seed=seed + 50,
            index_name="synthetic-tombstoned",
            location=redact_secrets("calibration://synthetic-tombstoned"),
        )
        return _PreparedCorpus(
            dataset_id="synthetic-tombstoned",
            family="synthetic",
            adapter=adapter,
            search_params={"nprobe": 1, "ef_search": 8},
            n_lists=8,
        )
    raise DatasetSkippedError(f"synthetic-{name}", f"unknown smoke synthetic {name!r}")


def _format_value(result: MetricResult) -> str:
    if result.state is MetricState.UNAVAILABLE or result.value is None:
        return ""
    return f"{result.value:.10g}"


def _metric_row(
    *,
    kind: str,
    family: str,
    dataset_id: str,
    n: int,
    dimension: int,
    metric_space: str,
    index_kind: str,
    config: AuditConfig,
    n_lists: int,
    result: MetricResult,
    verdict: str,
    profile: str,
    hubness_sample_size: int,
) -> dict[str, str]:
    return {
        "kind": kind,
        "family": family,
        "dataset_id": dataset_id,
        "n": str(n),
        "dimension": str(dimension),
        "metric_space": metric_space,
        "index_kind": index_kind,
        "hubness_sample_size": str(hubness_sample_size),
        "k_hub": str(config.k_hub),
        "k": str(config.k),
        "queries": str(config.queries),
        "n_lists": str(n_lists),
        "metric_id": result.id,
        "state": result.state.value,
        "value": _format_value(result),
        "unavailable_reason": result.unavailable_reason or "",
        "evidence_strength": result.evidence_strength.value,
        "verdict": verdict,
        "seed": str(config.seed),
        "profile": profile,
    }


def _audit_config(
    profile: Profile, *, hubness_sample_size: int, k_hub: int, hubness_only: bool
) -> AuditConfig:
    enabled = {
        CANARY_METRIC_ID: not hubness_only,
        HUB_SHARE_METRIC_ID: True,
        ANTIHUB_METRIC_ID: True,
        DFI_METRIC_ID: not hubness_only,
        PARTITION_CV_METRIC_ID: not hubness_only,
    }
    return AuditConfig(
        seed=profile.seed,
        queries=profile.queries,
        k=profile.k,
        hubness_sample_size=hubness_sample_size,
        k_hub=k_hub,
        metrics_enabled=enabled,
    )


def _run_corpus(
    prepared: _PreparedCorpus,
    profile: Profile,
    *,
    hubness_sample_size: int,
    k_hub: int,
    hubness_only: bool,
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    adapter = prepared.adapter
    config = _audit_config(
        profile,
        hubness_sample_size=hubness_sample_size,
        k_hub=k_hub,
        hubness_only=hubness_only,
    )
    report = run_audit(adapter, config, search_params=prepared.search_params)
    descriptor = adapter.descriptor
    counts = adapter.counts()
    n = int(counts.live)
    dimension = int(descriptor.dimension)
    space = descriptor.metric_space.value
    kind = descriptor.index_kind.value
    share = metric_by_id(report, HUB_SHARE_METRIC_ID)
    anti = metric_by_id(report, ANTIHUB_METRIC_ID)
    actual_s = hubness_sample_size
    if share is not None and share.sampling.get("S") is not None:
        actual_s = int(share.sampling["S"])
    baseline_rows: list[dict[str, str]] = []
    if not hubness_only:
        for metric_id in sorted(FIVE_METRICS):
            result = metric_by_id(report, metric_id)
            if result is None:
                continue
            baseline_rows.append(
                _metric_row(
                    kind="baseline",
                    family=prepared.family,
                    dataset_id=prepared.dataset_id,
                    n=n,
                    dimension=dimension,
                    metric_space=space,
                    index_kind=kind,
                    config=config,
                    n_lists=prepared.n_lists,
                    result=result,
                    verdict=report.verdict.value,
                    profile=profile.name,
                    hubness_sample_size=actual_s,
                )
            )
    sensitivity: dict[str, str] | None = None
    if share is not None and anti is not None:
        sensitivity = {
            "family": prepared.family,
            "dataset_id": prepared.dataset_id,
            "n": str(n),
            "dimension": str(dimension),
            "hubness_sample_size": str(actual_s),
            "k_hub": str(k_hub),
            "hub_share_top1pct": _format_value(share),
            "hub_share_state": share.state.value,
            "hub_share_reason": share.unavailable_reason or "",
            "antihub_fraction": _format_value(anti),
            "antihub_state": anti.state.value,
            "antihub_reason": anti.unavailable_reason or "",
            "seed": str(profile.seed),
            "profile": profile.name,
        }
    return baseline_rows, sensitivity


def _write_csv(
    path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        rows,
        key=lambda r: tuple(r.get(col, "") for col in columns),
    )
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in ordered:
            writer.writerow({col: row.get(col, "") for col in columns})


def write_datasets_md(path: Path) -> None:
    """Render the licence catalog. Regenerable; do not hand-edit numbers here."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Calibration datasets",
        "",
        "Licences and provenance for every corpus the P8-01 harness knows about.",
        "Source vectors are **not** in git. Derived statistics live in `results.csv`.",
        "",
        "Regenerate this file with `uv run python scripts/calibrate.py --profile smoke --out docs/calibration` "
        "(catalogue only changes when `CATALOG` in `scripts/calibrate.py` changes).",
        "",
        "| ID | Family | Status | SPDX | Licence (short) | Provenance |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for spec in CATALOG:
        licence = spec.licence.replace("|", "\\|").replace("\n", " ")
        if len(licence) > 140:
            licence = licence[:137] + "..."
        prov = spec.provenance.replace("|", "\\|")
        if len(prov) > 120:
            prov = prov[:117] + "..."
        lines.append(
            f"| `{spec.id}` | {spec.family} | {spec.status} | `{spec.spdx}` | {licence} | {prov} |"
        )
    lines.extend(["", "## Notes", ""])
    for spec in CATALOG:
        if spec.notes:
            lines.append(f"- **{spec.id}:** {spec.notes}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_dataset_report(
    path: Path, dataset_id: str, rows: Sequence[Mapping[str, str]]
) -> None:
    spec = _CATALOG_BY_ID.get(dataset_id)
    title = spec.title if spec is not None else dataset_id
    lines = [
        f"# {dataset_id}",
        "",
        title,
        "",
        "| Metric | State | Value | Unavailable reason |",
        "| :--- | :--- | ---: | :--- |",
    ]
    for row in sorted(rows, key=lambda r: r.get("metric_id", "")):
        if row.get("kind") != "baseline":
            continue
        lines.append(
            f"| `{row['metric_id']}` | {row['state']} | {row['value'] or '—'} | "
            f"{row['unavailable_reason'] or '—'} |"
        )
    if spec is not None:
        lines.extend(
            [
                "",
                f"Licence: {spec.licence}",
                "",
                f"Provenance: {spec.provenance}",
            ]
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_sensitivity_report(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    lines = [
        "# Hubness sampling sensitivity",
        "",
        "Gaussian control only. Each cell is a measured hubness pair at that "
        "`hubness_sample_size` x `k_hub`. Empty value = `UNAVAILABLE` (never `0.0`).",
        "",
        "| Dataset | d | S | k_hub | hub_share_top1pct | antihub_fraction |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(
        rows,
        key=lambda r: (
            r.get("dataset_id", ""),
            int(r.get("dimension") or 0),
            int(r.get("hubness_sample_size") or 0),
            int(r.get("k_hub") or 0),
        ),
    ):
        lines.append(
            f"| `{row['dataset_id']}` | {row['dimension']} | {row['hubness_sample_size']} | "
            f"{row['k_hub']} | {row['hub_share_top1pct'] or '—'} | {row['antihub_fraction'] or '—'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _prepare_public(
    dataset_id: str,
    profile: Profile,
    cache: Path,
) -> _PreparedCorpus:
    spec = _CATALOG_BY_ID[dataset_id]
    if spec.status == "excluded":
        raise DatasetSkippedError(dataset_id, spec.notes or "excluded by licence")
    space = MetricSpace[spec.metric_space]
    if dataset_id == "sift-128":
        vectors = _load_sift(spec, cache, profile.n, profile.allow_download)
    elif dataset_id == "gist-960":
        vectors = _load_gist(spec, cache, profile.n, profile.allow_download)
    elif dataset_id == "glove-100":
        vectors = _load_glove(spec, cache, profile.n, profile.allow_download)
    elif dataset_id == "sentence-minilm":
        vectors = _load_sentence_npy(spec, cache, profile.n)
    else:
        raise DatasetSkippedError(dataset_id, "no loader")
    adapter = _calibration_adapter(
        dataset_id, vectors, metric_space=space, seed=profile.seed
    )
    return _PreparedCorpus(
        dataset_id=dataset_id,
        family="public",
        adapter=adapter,
        search_params={"exact": True},
        n_lists=_n_lists_for(int(vectors.shape[0])),
    )


def run_profile(
    profile: Profile,
    *,
    out_dir: Path,
    cache_dir: Path | None = None,
) -> RunArtefacts:
    """Run one calibration profile and write CSV + markdown under ``out_dir``."""
    cache = _cache_dir(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_rows: list[dict[str, str]] = []
    sensitivity_rows: list[dict[str, str]] = []
    skipped_rows: list[dict[str, str]] = []

    gauss_n = max(profile.n, max(profile.hubness_sample_sizes))
    for dim in profile.gaussian_dims:
        dataset_id = f"gaussian-{dim}"
        sys.stderr.write(f"calibrate: {dataset_id} n={gauss_n}\n")
        vectors = _gaussian_vectors(gauss_n, dim, profile.seed + dim)
        adapter = _calibration_adapter(
            dataset_id,
            vectors,
            metric_space=MetricSpace.L2,
            seed=profile.seed,
        )
        prepared = _PreparedCorpus(
            dataset_id=dataset_id,
            family="gaussian",
            adapter=adapter,
            search_params={"exact": True},
            n_lists=_n_lists_for(gauss_n),
        )
        try:
            base, _sens = _run_corpus(
                prepared,
                profile,
                hubness_sample_size=profile.baseline_hubness_sample_size,
                k_hub=profile.baseline_k_hub,
                hubness_only=False,
            )
            baseline_rows.extend(base)
            for sample_size in profile.hubness_sample_sizes:
                for k_hub in profile.k_hubs:
                    _b, sens = _run_corpus(
                        prepared,
                        profile,
                        hubness_sample_size=sample_size,
                        k_hub=k_hub,
                        hubness_only=True,
                    )
                    if sens is not None:
                        sensitivity_rows.append(sens)
        finally:
            adapter.close()

    for name in profile.synthetic_names:
        sys.stderr.write(f"calibrate: synthetic-{name}\n")
        prepared = None
        try:
            if profile.synthetic_size == "smoke":
                prepared = _smoke_synthetic(name, profile.seed)
            else:
                size = _SCENARIO_SIZES.get(profile.synthetic_size, "small")
                opened = open_scenario(name, size=size)
                prepared = _PreparedCorpus(
                    dataset_id=f"synthetic-{name}",
                    family="synthetic",
                    adapter=opened.adapter,
                    search_params=_search_params_from_spec(
                        opened.spec.default_search_params
                    ),
                    n_lists=int(opened.spec.n_lists or 0),
                )
            assert prepared is not None
            base, _s = _run_corpus(
                prepared,
                profile,
                hubness_sample_size=profile.baseline_hubness_sample_size,
                k_hub=profile.baseline_k_hub,
                hubness_only=False,
            )
            baseline_rows.extend(base)
        except DatasetSkippedError as exc:
            skipped_rows.append(
                {
                    "dataset_id": exc.dataset_id,
                    "family": "synthetic",
                    "reason": exc.reason,
                }
            )
        finally:
            if prepared is not None:
                prepared.adapter.close()

    if profile.include_public:
        for dataset_id in profile.public_ids:
            spec = _CATALOG_BY_ID.get(dataset_id)
            if spec is not None and spec.status == "excluded":
                skipped_rows.append(
                    {
                        "dataset_id": dataset_id,
                        "family": "public",
                        "reason": spec.notes or "excluded by licence",
                    }
                )
                continue
            prepared = None
            try:
                sys.stderr.write(f"calibrate: {dataset_id}\n")
                prepared = _prepare_public(dataset_id, profile, cache)
                base, _s = _run_corpus(
                    prepared,
                    profile,
                    hubness_sample_size=profile.baseline_hubness_sample_size,
                    k_hub=profile.baseline_k_hub,
                    hubness_only=False,
                )
                baseline_rows.extend(base)
            except DatasetSkippedError as exc:
                skipped_rows.append(
                    {
                        "dataset_id": exc.dataset_id,
                        "family": "public",
                        "reason": exc.reason,
                    }
                )
            finally:
                if prepared is not None:
                    prepared.adapter.close()

    results_csv = out_dir / "results.csv"
    sensitivity_csv = out_dir / "hubness_sensitivity.csv"
    skipped_csv = out_dir / "skipped.csv"
    datasets_md = out_dir / "datasets.md"
    _write_csv(results_csv, CSV_COLUMNS, baseline_rows)
    _write_csv(sensitivity_csv, SENSITIVITY_COLUMNS, sensitivity_rows)
    _write_csv(skipped_csv, SKIPPED_COLUMNS, skipped_rows)
    write_datasets_md(datasets_md)
    reports_dir = out_dir / "reports"
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in baseline_rows:
        by_id.setdefault(row["dataset_id"], []).append(row)
    for dataset_id, group in by_id.items():
        _write_dataset_report(reports_dir / f"{dataset_id}.md", dataset_id, group)
    _write_sensitivity_report(out_dir / "hubness_sensitivity.md", sensitivity_rows)
    return RunArtefacts(
        results_csv=results_csv,
        sensitivity_csv=sensitivity_csv,
        skipped_csv=skipped_csv,
        datasets_md=datasets_md,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P8-01 calibration harness")
    parser.add_argument(
        "--profile",
        choices=("smoke", "reference"),
        default="smoke",
        help="smoke = default-suite scale; reference = published calibration",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/calibration"),
        help="directory for CSV and markdown",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="public dataset cache (default ~/.cache/vhecfsck/calibration)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="never fetch public archives; skip with a reason instead",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    profile = PROFILE_SMOKE if args.profile == "smoke" else PROFILE_REFERENCE
    if args.no_download:
        profile = Profile(**{**profile.__dict__, "allow_download": False})
    artefacts = run_profile(profile, out_dir=args.out, cache_dir=args.cache)
    sys.stderr.write(f"wrote {artefacts.results_csv}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
