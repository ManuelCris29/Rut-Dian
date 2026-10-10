"""Pruebas de `infra.retention.find_expired` (aviso de la CLI; T-44 la reutiliza)."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rut_checker.infra.retention import find_expired

BOGOTA = ZoneInfo("America/Bogota")
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=BOGOTA)


def _touch(path: Path, mtime: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    if mtime is not None:
        stamp = mtime.timestamp()
        os.utime(path, (stamp, stamp))
    return path


def test_age_comes_from_run_id_not_mtime(tmp_path: Path) -> None:
    # run_id viejo (2025-01-01) con mtime reciente: vencido por el run_id.
    old = _touch(tmp_path / "resultado_20250101-100000-abcd.xlsx", NOW)
    # run_id reciente con mtime antiguo: NO vencido.
    recent = _touch(tmp_path / "run_20261001-100000-abcd.jsonl", NOW - timedelta(days=900))
    assert find_expired([tmp_path], NOW, 365) == [old]
    assert recent not in find_expired([tmp_path], NOW, 365)


def test_file_without_run_id_uses_mtime(tmp_path: Path) -> None:
    stale = _touch(tmp_path / "entrada.csv", NOW - timedelta(days=400))
    fresh = _touch(tmp_path / "otra.csv", NOW - timedelta(days=10))
    expired = find_expired([tmp_path], NOW, 365)
    assert stale in expired
    assert fresh not in expired


def test_boundary_is_strictly_older_than_max_age(tmp_path: Path) -> None:
    exact = _touch(tmp_path / "run_20251010-120000-abcd.jsonl")
    older = _touch(tmp_path / "run_20251010-115900-abcd.jsonl")
    assert find_expired([tmp_path], NOW, 365) == [older]
    assert exact not in find_expired([tmp_path], NOW, 365)


def test_missing_dirs_are_ignored_and_subdirs_are_scanned(tmp_path: Path) -> None:
    nested = _touch(tmp_path / "sub" / "resultado_20240101-000000-0000.xlsx")
    assert find_expired([tmp_path / "no_existe", tmp_path], NOW, 365) == [nested]


def test_impossible_run_id_date_falls_back_to_mtime(tmp_path: Path) -> None:
    odd = _touch(tmp_path / "run_20269999-000000-abcd.jsonl", NOW - timedelta(days=2))
    assert odd not in find_expired([tmp_path], NOW, 365)
