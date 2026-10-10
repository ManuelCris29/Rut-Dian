"""Pruebas de `infra.retention`: detección de vencidos y purga (T-44, ARQUITECTURA §11)."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from rut_checker.domain.status import SourceKind
from rut_checker.infra import retention
from rut_checker.infra.purge_keys import FileKind, Folder
from rut_checker.infra.retention import (
    count_by_bucket,
    file_kind,
    find_expired,
    plan_purge,
    purge,
)
from rut_checker.infra.run_source import read_run_source

BOGOTA = ZoneInfo("America/Bogota")
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=BOGOTA)
OLD_RUN = "20250101-100000-abcd"
RECENT_RUN = "20261001-100000-abcd"
PORTAL_RUN = "20261005-100000-aaaa"
FAKE_RUN = "20261005-110000-bbbb"
PORTAL = SourceKind.PORTAL_DIAN_C1
ORIGINAL_LATEST_TIME = retention._latest_time
HOUR = timedelta(hours=1)


@pytest.fixture(autouse=True)
def file_date_is_mtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """En las pruebas la fecha del archivo es su mtime (ctime/creación serían siempre "ahora")."""
    monkeypatch.setattr(retention, "_latest_time", lambda st: st.st_mtime)


def _touch(path: Path, mtime: datetime | None = None, text: str = "x") -> Path:
    """Crea el archivo; sin `mtime` queda con una hora de antigüedad respecto a NOW."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = (mtime or NOW - HOUR).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _run_log(
    directory: Path, run_id: str, source: SourceKind, mtime: datetime | None = None
) -> Path:
    event = {"event": "run_started", "run_id": run_id, "source": source.value}
    return _touch(directory / f"run_{run_id}.jsonl", mtime, text=json.dumps(event) + "\n")


def test_age_comes_from_run_id_not_mtime(tmp_path: Path) -> None:
    # run_id viejo (2025-01-01) con mtime reciente: vencido por el run_id.
    old = _touch(tmp_path / f"resultado_{OLD_RUN}.xlsx", NOW)
    # run_id reciente con mtime antiguo: NO vencido.
    recent = _touch(tmp_path / f"run_{RECENT_RUN}.jsonl", NOW - timedelta(days=900))
    assert find_expired([tmp_path], NOW) == [old]
    assert recent not in find_expired([tmp_path], NOW)


def test_file_without_run_id_uses_file_date(tmp_path: Path) -> None:
    stale = _touch(tmp_path / "entrada.csv", NOW - timedelta(days=400))
    fresh = _touch(tmp_path / "otra.csv", NOW - timedelta(days=10))
    expired = find_expired([tmp_path], NOW)
    assert stale in expired
    assert fresh not in expired


def test_file_date_is_latest_of_mtime_ctime_and_birth() -> None:
    def stat(mtime: float, ctime: float) -> os.stat_result:
        return os.stat_result((0o100644, 0, 0, 1, 0, 0, 1, 0, int(mtime), int(ctime)))

    assert ORIGINAL_LATEST_TIME(stat(100, 900)) == 900
    assert ORIGINAL_LATEST_TIME(stat(900, 100)) == 900


def test_old_mtime_with_recent_creation_is_not_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retention, "_latest_time", ORIGINAL_LATEST_TIME)
    copied = _touch(tmp_path / "entrada.csv", NOW - timedelta(days=900))
    # El archivo se acaba de crear (ctime/creación = ahora real, posterior a NOW - 365 días).
    real_now = datetime.now(BOGOTA)
    assert find_expired([tmp_path], real_now) == []
    assert copied.exists()


def test_boundary_is_strictly_older_than_max_age(tmp_path: Path) -> None:
    exact = _touch(tmp_path / "run_20251010-120000-abcd.jsonl")
    older = _touch(tmp_path / "run_20251010-115900-abcd.jsonl")
    assert find_expired([tmp_path], NOW, max_age_days=365) == [older]
    assert exact not in find_expired([tmp_path], NOW, max_age_days=365)


def test_missing_dirs_are_ignored_and_subdirs_are_scanned(tmp_path: Path) -> None:
    nested = _touch(tmp_path / "sub" / "resultado_20240101-000000-0000.xlsx")
    assert find_expired([tmp_path / "no_existe", tmp_path], NOW) == [nested]


def test_impossible_run_id_date_falls_back_to_file_date(tmp_path: Path) -> None:
    odd = _touch(tmp_path / "run_20269999-000000-abcd.jsonl", NOW - timedelta(days=2))
    assert odd not in find_expired([tmp_path], NOW)


def test_future_run_id_is_not_trusted(tmp_path: Path) -> None:
    future = _touch(tmp_path / "run_20991231-100000-abcd.jsonl", NOW - timedelta(days=400))
    assert find_expired([tmp_path], NOW) == [future]
    soon = _touch(tmp_path / "run_20261010-130000-abcd.jsonl", NOW - timedelta(days=400))
    assert soon not in find_expired([tmp_path], NOW)  # dentro de la tolerancia de un día


@pytest.mark.parametrize(
    "name",
    [
        f"copia_resultado_{OLD_RUN}.xlsx",
        f"resultado_{OLD_RUN}.xlsx.bak",
        f"nota_{OLD_RUN}.txt",
        f"resultado_{OLD_RUN}_2.xlsx",
        f"run_{OLD_RUN}.jsonl.old",
        f"snapshot_{OLD_RUN}.html",
        f"x{OLD_RUN}.csv",
    ],
)
def test_names_that_only_contain_a_run_id_fall_back_to_file_date(tmp_path: Path, name: str) -> None:
    misleading = _touch(tmp_path / name, NOW - timedelta(days=10))
    assert misleading not in find_expired([tmp_path], NOW)
    assert file_kind(misleading) is FileKind.OTHER


def test_snapshots_expire_after_30_days(tmp_path: Path) -> None:
    old_snapshot = _touch(tmp_path / "snapshot_20260901-100000-abcd_1.html")  # 39 días
    young_snapshot = _touch(tmp_path / "snapshot_20260925-100000-abcd_1.html")  # 15 días
    same_age_result = _touch(tmp_path / "resultado_20260901-100000-abcd.xlsx")
    expired = find_expired([tmp_path], NOW)
    assert old_snapshot in expired
    assert young_snapshot not in expired
    assert same_age_result not in expired


def test_snapshot_limit_never_exceeds_configured_retention(tmp_path: Path) -> None:
    snapshot = _touch(tmp_path / "snapshot_20260925-100000-abcd_1.html")  # 15 días
    assert snapshot in find_expired([tmp_path], NOW, max_age_days=10)


def test_filter_by_portal_source_ignores_age(tmp_path: Path) -> None:
    logs, output = tmp_path / "logs", tmp_path / "output"
    portal_log = _run_log(logs, PORTAL_RUN, PORTAL)
    portal_result = _touch(output / f"resultado_{PORTAL_RUN}.xlsx")
    portal_alt = _touch(output / f"resultado_{PORTAL_RUN}_1.xlsx")
    portal_backup = _touch(output / f"resultado_{PORTAL_RUN}.json")
    portal_snapshot = _touch(logs / f"snapshot_{PORTAL_RUN}_0.html")
    fake_log = _run_log(logs, FAKE_RUN, SourceKind.FAKE)
    fake_result = _touch(output / f"resultado_{FAKE_RUN}.xlsx")
    stray = _touch(output / "otro.csv")
    found = find_expired([logs, output], NOW, PORTAL)
    expected = [portal_log, portal_result, portal_alt, portal_backup, portal_snapshot]
    assert sorted(found) == sorted(expected)
    assert not {fake_log, fake_result, stray} & set(found)


def test_source_mode_matches_only_exact_names(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    _run_log(logs, PORTAL_RUN, PORTAL)
    tricky = [
        _touch(logs / f"copia_resultado_{PORTAL_RUN}.xlsx"),
        _touch(logs / f"resultado_{PORTAL_RUN}.xlsx.bak"),
        _touch(logs / f"nota_{PORTAL_RUN}.txt"),
    ]
    plan = plan_purge([logs], NOW, PORTAL)
    assert not set(tricky) & set(plan.selected)
    assert not set(tricky) & set(plan.unknown_source)


def test_source_mode_excludes_data_dirs(tmp_path: Path) -> None:
    logs, data = tmp_path / "logs", tmp_path / "data"
    _run_log(logs, PORTAL_RUN, PORTAL)
    kept = _touch(data / f"resultado_{PORTAL_RUN}.xlsx")
    plan = plan_purge([logs, data], NOW, PORTAL, source_excluded=[data])
    assert kept not in plan.selected
    assert kept not in plan.unknown_source


def test_source_mode_finds_results_in_output_subfolders(tmp_path: Path) -> None:
    logs, output = tmp_path / "logs", tmp_path / "output"
    _run_log(logs, PORTAL_RUN, PORTAL)
    nested = _touch(output / "area" / f"resultado_{PORTAL_RUN}.xlsx")
    assert nested in find_expired([logs, output], NOW, PORTAL)


def test_orphans_without_log_are_reported_not_selected(tmp_path: Path) -> None:
    logs, output = tmp_path / "logs", tmp_path / "output"
    orphan = _touch(output / f"resultado_{PORTAL_RUN}.xlsx")
    unreadable = _touch(logs / f"run_{FAKE_RUN}.jsonl", text="basura\n")
    orphan_of_unreadable = _touch(output / f"resultado_{FAKE_RUN}.xlsx")
    plan = plan_purge([logs, output], NOW, PORTAL)
    assert plan.selected == []
    assert sorted(plan.unknown_source) == sorted([orphan, unreadable, orphan_of_unreadable])
    assert find_expired([logs, output], NOW, PORTAL) == []


def test_source_mode_skips_files_modified_in_last_10_minutes(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    busy_log = _run_log(logs, PORTAL_RUN, PORTAL, NOW - timedelta(minutes=5))
    busy_result = _touch(logs / f"resultado_{PORTAL_RUN}.xlsx", NOW - timedelta(minutes=5))
    quiet = _touch(logs / f"resultado_{PORTAL_RUN}_1.xlsx", NOW - timedelta(minutes=11))
    plan = plan_purge([logs], NOW, PORTAL)
    assert plan.selected == [quiet]
    assert busy_log not in plan.selected + plan.unknown_source
    assert busy_result not in plan.selected + plan.unknown_source


def test_filter_by_source_skips_runs_without_valid_run_started(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    garbage = 'no es json\n\x00\x01\n{"event": 5}\n[1, 2]\n'
    bad = _touch(logs / f"run_{PORTAL_RUN}.jsonl", text=garbage)
    _touch(logs / f"resultado_{PORTAL_RUN}.xlsx")
    assert find_expired([logs], NOW, PORTAL) == []
    assert read_run_source(bad) is None


def test_read_run_source_tolerates_invalid_lines_and_huge_lines(tmp_path: Path) -> None:
    started = {"event": "run_started", "source": "PORTAL_DIAN_C1"}
    content = "basura\n" + "x" * 300_000 + "\n" + json.dumps(started) + "\n"
    path = _touch(tmp_path / f"run_{PORTAL_RUN}.jsonl", text=content)
    assert read_run_source(path) is PORTAL


def test_read_run_source_with_unknown_source_is_none(tmp_path: Path) -> None:
    event = {"event": "run_started", "source": "OTRA"}
    path = _touch(tmp_path / f"run_{PORTAL_RUN}.jsonl", text=json.dumps(event))
    assert read_run_source(path) is None


def test_temp_files_expire_after_one_day_whatever_their_run_id(tmp_path: Path) -> None:
    stale = _touch(tmp_path / f".resultado_{RECENT_RUN}.tmp.xlsx", NOW - timedelta(days=2))
    fresh = _touch(tmp_path / f".resultado_{RECENT_RUN}_1.tmp.xlsx", NOW - HOUR)
    assert find_expired([tmp_path], NOW) == [stale]
    assert fresh.exists()


def test_fresh_temp_of_selected_source_is_kept(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    _run_log(logs, PORTAL_RUN, PORTAL)
    fresh = _touch(logs / f".resultado_{PORTAL_RUN}.tmp.xlsx", NOW - HOUR)
    stale = _touch(logs / f".resultado_{PORTAL_RUN}_1.tmp.xlsx", NOW - timedelta(days=3))
    found = find_expired([logs], NOW, PORTAL)
    assert stale in found
    assert fresh not in found


def test_overlapping_dirs_do_not_duplicate_paths(tmp_path: Path) -> None:
    old = _touch(tmp_path / "sub" / f"resultado_{OLD_RUN}.xlsx")
    assert find_expired([tmp_path, tmp_path / "sub"], NOW) == [old]


def test_placeholder_files_are_never_candidates(tmp_path: Path) -> None:
    _touch(tmp_path / ".gitkeep", NOW - timedelta(days=900))
    assert find_expired([tmp_path], NOW) == []


def test_symlinked_directories_are_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "fuera"
    victim = _touch(outside / f"resultado_{OLD_RUN}.xlsx")
    root = tmp_path / "output"
    root.mkdir()
    try:
        (root / "enlace").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("sin permiso para crear enlaces simbólicos")
    assert find_expired([root], NOW) == []
    assert victim.exists()


def test_symlinked_files_are_not_candidates(tmp_path: Path) -> None:
    target = _touch(tmp_path / "fuera" / f"resultado_{OLD_RUN}.xlsx")
    root = tmp_path / "output"
    root.mkdir()
    try:
        (root / f"resultado_{OLD_RUN}.xlsx").symlink_to(target)
    except OSError:
        pytest.skip("sin permiso para crear enlaces simbólicos")
    assert find_expired([root], NOW) == []


def test_file_kind_classification() -> None:
    assert file_kind(Path(f"resultado_{OLD_RUN}.xlsx")) is FileKind.RESULT
    assert file_kind(Path(f"resultado_{OLD_RUN}_1.xlsx")) is FileKind.RESULT
    assert file_kind(Path(f"resultado_{OLD_RUN}.json")) is FileKind.RESULT
    assert file_kind(Path(f"run_{OLD_RUN}.jsonl")) is FileKind.RUN_LOG
    assert file_kind(Path(f"snapshot_{OLD_RUN}_1.html")) is FileKind.SNAPSHOT
    assert file_kind(Path(f".resultado_{OLD_RUN}.tmp.xlsx")) is FileKind.TEMP
    assert file_kind(Path("entrada.csv")) is FileKind.OTHER


def test_count_by_bucket_groups_by_folder_and_kind(tmp_path: Path) -> None:
    roots = [(Folder.DATA, tmp_path / "data"), (Folder.OUTPUT, tmp_path / "output")]
    paths = [
        tmp_path / "data" / "entrada.csv",
        tmp_path / "output" / f"resultado_{OLD_RUN}.xlsx",
        tmp_path / "output" / f"resultado_{OLD_RUN}_1.xlsx",
    ]
    assert count_by_bucket(paths, roots) == {"data.otro": 1, "output.resultado": 2}


def test_purge_deletes_files_and_counts_them(tmp_path: Path) -> None:
    first = _touch(tmp_path / f"resultado_{OLD_RUN}.xlsx")
    second = _touch(tmp_path / f"run_{OLD_RUN}.jsonl")
    result = purge([first, second], within=[tmp_path])
    assert (result.deleted, result.failed) == (2, 0)
    assert not first.exists()
    assert not second.exists()


def test_purge_never_deletes_outside_roots(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    outside = _touch(tmp_path / "fuera.txt")
    result = purge([outside], within=[root])
    assert (result.deleted, result.failed) == (0, 1)
    assert outside.exists()


def test_purge_missing_files_are_not_failures(tmp_path: Path) -> None:
    gone = tmp_path / f"resultado_{OLD_RUN}.xlsx"
    kept = _touch(tmp_path / f"run_{OLD_RUN}.jsonl")
    result = purge([gone, kept], within=[tmp_path])
    assert (result.deleted, result.failed) == (1, 0)


def test_purge_counts_permission_errors_as_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = _touch(tmp_path / f"resultado_{OLD_RUN}.xlsx")
    free = _touch(tmp_path / f"run_{OLD_RUN}.jsonl")
    original = Path.unlink

    def fake_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == locked:
            raise PermissionError
        original(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    result = purge([locked, free], within=[tmp_path])
    assert (result.deleted, result.failed) == (1, 1)
    assert locked.exists()


def test_purge_skips_symlinks_and_keeps_target(tmp_path: Path) -> None:
    target = _touch(tmp_path / "fuera" / "dato.txt")
    root = tmp_path / "output"
    root.mkdir()
    link = root / "enlace.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("sin permiso para crear enlaces simbólicos")
    result = purge([link], within=[root])
    assert (result.deleted, result.failed) == (0, 1)
    assert target.exists()
