"""P1-06: adapter registry and target URI resolution."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.adapters.registry import (
    SUPPORTED_SCHEMES,
    open_target,
    register,
    registered_schemes,
    resolve_class,
)
from vhecfsck.adapters.synthetic_adapter import SyntheticAdapter
from vhecfsck.errors import UsageError


@contextmanager
def _without_module(name: str) -> Iterator[None]:
    """Force ImportError for ``name`` even if already importable."""
    sentinel = object()
    previous = sys.modules.get(name, sentinel)
    sys.modules[name] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if previous is sentinel:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous  # type: ignore[assignment]


def test_synthetic_scheme_resolves_class_and_opens() -> None:
    assert resolve_class("synthetic://tiny") is SyntheticAdapter
    adapter = open_target("synthetic://tiny")
    assert isinstance(adapter, IndexAdapter)
    assert isinstance(adapter, SyntheticAdapter)
    assert adapter.descriptor.index_name == "tiny"
    adapter.close()


def test_lance_uri_and_bare_path_resolve_class_without_sdk() -> None:
    before = "lancedb" in sys.modules
    assert resolve_class("lance:///tmp/data.lance") is LanceDBAdapter
    assert resolve_class("/var/lib/vectors.lance") is LanceDBAdapter
    assert resolve_class("./local.lance") is LanceDBAdapter
    if not before:
        assert "lancedb" not in sys.modules


def test_qdrant_and_postgres_resolve_class_without_sdk() -> None:
    before_q = "qdrant_client" in sys.modules
    before_pg = "psycopg" in sys.modules
    assert resolve_class("qdrant://localhost:6333/mycol") is QdrantAdapter
    assert (
        resolve_class("postgres://u:p@localhost:5432/db?table=t&column=v")
        is PostgresAdapter
    )
    if not before_q:
        assert "qdrant_client" not in sys.modules
    if not before_pg:
        assert "psycopg" not in sys.modules


def test_missing_qdrant_extra_gives_install_hint() -> None:
    with (
        _without_module("qdrant_client"),
        pytest.raises(UsageError) as excinfo,
    ):
        open_target("qdrant://127.0.0.1:6333/c")
    err = excinfo.value
    assert err.exit_code == 4
    joined = f"{err} {err.hint}"
    assert 'pip install "vhecfsck[qdrant]"' in joined
    assert "ImportError" not in joined
    assert "Traceback" not in joined


def test_missing_lancedb_extra_gives_install_hint() -> None:
    with (
        _without_module("lancedb"),
        pytest.raises(UsageError) as excinfo,
    ):
        open_target("lance:///tmp/x.lance")
    assert 'pip install "vhecfsck[lancedb]"' in f"{excinfo.value} {excinfo.value.hint}"


def test_missing_postgres_extra_gives_install_hint() -> None:
    with (
        _without_module("psycopg"),
        pytest.raises(UsageError) as excinfo,
    ):
        open_target("postgres://u:p@localhost/db?table=t&column=emb")
    assert 'pip install "vhecfsck[postgres]"' in f"{excinfo.value} {excinfo.value.hint}"


def test_credentials_never_appear_in_error_message() -> None:
    secret = "s3cret-should-not-leak"
    target = f"postgres://alice:{secret}@db.example:5432/app?table=t&column=v"
    with (
        _without_module("psycopg"),
        pytest.raises(UsageError) as excinfo,
    ):
        open_target(target)
    err = excinfo.value
    assert secret not in str(err)
    assert secret not in err.hint
    assert secret not in repr(err)


def test_unknown_scheme_lists_supported() -> None:
    with pytest.raises(UsageError) as excinfo:
        open_target("redis://localhost:6379/0")
    err = excinfo.value
    assert err.exit_code == 4
    msg = str(err)
    for scheme in SUPPORTED_SCHEMES:
        assert scheme in msg
    # Registration surface stays in sync.
    assert set(registered_schemes()) == set(SUPPORTED_SCHEMES)


def test_register_extends_without_editing_resolve_chain() -> None:
    class _Stub:
        pass

    def _open(_target: str) -> IndexAdapter:
        raise AssertionError("should not open")

    register("probe", adapter_class=_Stub, opener=_open)
    try:
        assert resolve_class("probe://x") is _Stub
        assert "probe" in registered_schemes()
    finally:
        # Leave builtins intact for later tests in the same process.
        from vhecfsck.adapters import registry as reg

        reg._ENTRIES.pop("probe", None)
