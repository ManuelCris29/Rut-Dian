"""Pruebas e2e del comando `purgar` (T-44) con `CliRunner`, en un proyecto temporal."""

import json
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rut_checker.cli import app
from rut_checker.infra import retention

runner = CliRunner()
OLD_RUN = "20240101-100000-abcd"
RECENT_RUN = "20261001-100000-abcd"
PORTAL_RUN = "20261005-100000-aaaa"
FAKE_RUN = "20261005-110000-bbbb"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Proyecto temporal con carpetas por defecto ignoradas por git."""
    (tmp_path / ".gitignore").write_text("output/\nlogs/\ndata/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    root = logging.getLogger()
    saved = list(root.handlers)
    yield tmp_path
    root.handlers[:] = saved


@pytest.fixture(autouse=True)
def file_date_is_mtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """La fecha del archivo es su mtime (ctime/creación serían siempre "ahora")."""
    monkeypatch.setattr(retention, "_latest_time", lambda st: st.st_mtime)


def _touch(path: Path, text: str = "x", *, hours_old: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if hours_old:
        stamp = time.time() - hours_old * 3600
        os.utime(path, (stamp, stamp))
    return path


def _run_started(path: Path, source: str) -> Path:
    line = json.dumps({"event": "run_started", "source": source}) + chr(10)
    return _touch(path, line, hours_old=1)


def _purgar(*args: str) -> tuple[int, str, str]:
    result = runner.invoke(app, ["purgar", *args])
    return result.exit_code, result.stdout, result.stderr


def _maintenance_events(workspace: Path, *, skip: set[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for path in sorted((workspace / "logs").glob("run_*.jsonl")):
        if path.name in skip:
            continue
        events.extend(json.loads(line) for line in path.read_text("utf-8").splitlines())
    return events


def test_dry_run_deletes_nothing(workspace: Path) -> None:
    old_result = _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    old_log = _touch(workspace / "logs" / f"run_{OLD_RUN}.jsonl")
    old_input = _touch(workspace / "data" / "entrada.csv", hours_old=24 * 800)
    code, out, err = _purgar()
    assert code == 0
    assert old_result.exists()
    assert old_log.exists()
    assert old_input.exists()
    assert "--confirmar" in out
    assert "  output.resultado: 1" in out
    assert "Total: 3 archivos." in out
    # nunca nombres de archivo ni run_id
    assert OLD_RUN not in out + err
    assert "entrada.csv" not in out + err
    # la simulación no deja ningún log de mantenimiento
    assert [p.name for p in (workspace / "logs").glob("run_*.jsonl")] == [old_log.name]


def test_confirm_deletes_only_expired_and_logs_event(workspace: Path) -> None:
    old_result = _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    old_log = _touch(workspace / "logs" / f"run_{OLD_RUN}.jsonl")
    old_snapshot = _touch(workspace / "logs" / f"snapshot_{OLD_RUN}_1.html")
    recent = _touch(workspace / "output" / f"resultado_{RECENT_RUN}.xlsx")
    code, out, _ = _purgar("--confirmar")
    assert code == 0
    assert not old_result.exists()
    assert not old_log.exists()
    assert not old_snapshot.exists()
    assert recent.exists()
    assert "Total: 3 archivos." in out
    assert "Eliminados: 3." in out
    events = _maintenance_events(workspace, skip=set())
    assert [e["event"] for e in events] == ["purge_executed"]


def test_purge_event_has_counts(workspace: Path) -> None:
    _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    _touch(workspace / "output" / f"resultado_{OLD_RUN}_1.xlsx")
    _touch(workspace / "logs" / f"run_{OLD_RUN}.jsonl")
    code, _, _ = _purgar("--confirmar")
    assert code == 0
    (event,) = _maintenance_events(workspace, skip=set())
    assert event["event"] == "purge_executed"
    assert event["purge_counts"] == {
        "output.resultado": 2,
        "logs.log": 1,
        "deleted": 3,
        "failed": 0,
    }
    assert "source" not in event
    raw = " ".join(p.read_text("utf-8") for p in (workspace / "logs").glob("run_*.jsonl"))
    assert OLD_RUN not in raw
    assert "xlsx" not in raw


def test_maintenance_log_is_not_deleted_in_same_purge(workspace: Path) -> None:
    _touch(workspace / "logs" / f"run_{OLD_RUN}.jsonl")
    _purgar("--confirmar")
    remaining = list((workspace / "logs").glob("run_*.jsonl"))
    assert len(remaining) == 1
    assert OLD_RUN not in remaining[0].name


def test_fuente_portal_selects_only_portal_runs_regardless_of_age(workspace: Path) -> None:
    portal_log = _run_started(workspace / "logs" / f"run_{PORTAL_RUN}.jsonl", "PORTAL_DIAN_C1")
    portal_result = _touch(workspace / "output" / f"resultado_{PORTAL_RUN}.xlsx", hours_old=1)
    fake_log = _run_started(workspace / "logs" / f"run_{FAKE_RUN}.jsonl", "FAKE")
    fake_result = _touch(workspace / "output" / f"resultado_{FAKE_RUN}.xlsx", hours_old=1)
    old_result = _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    code, _, _ = _purgar("--fuente", "PORTAL_DIAN_C1", "--confirmar")
    assert code == 0
    assert not portal_log.exists()
    assert not portal_result.exists()
    assert fake_log.exists()
    assert fake_result.exists()
    assert old_result.exists()  # vencido por edad, pero --fuente solo toca la fuente pedida
    events = _maintenance_events(workspace, skip={fake_log.name})
    assert events[-1]["event"] == "purge_executed"
    assert events[-1]["source"] == "PORTAL_DIAN_C1"


def test_fuente_dry_run_deletes_nothing(workspace: Path) -> None:
    portal_log = _run_started(workspace / "logs" / f"run_{PORTAL_RUN}.jsonl", "PORTAL_DIAN_C1")
    code, out, _ = _purgar("--fuente", "PORTAL_DIAN_C1")
    assert code == 0
    assert portal_log.exists()
    assert "logs" in out


def test_nothing_to_purge_exits_zero(workspace: Path) -> None:
    code, out, _ = _purgar("--confirmar")
    assert code == 0
    assert "Total: 0 archivos." in out
    assert "Eliminados: 0." in out


def test_invalid_source_exits_2_without_echo(workspace: Path) -> None:
    code, out, err = _purgar("--fuente", "SECRETO1234")
    assert code == 2
    assert "SECRETO1234" not in out + err


def test_unsafe_folder_exits_2_and_deletes_nothing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (workspace / ".gitignore").unlink()
    (workspace / ".git").mkdir()
    old = _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    code, _, err = _purgar("--confirmar")
    assert code == 2
    assert old.exists()
    assert str(workspace) not in err


def test_symlinked_root_exits_2(workspace: Path) -> None:
    target = workspace / "fuera"
    victim = _touch(target / f"resultado_{OLD_RUN}.xlsx")
    try:
        (workspace / "output").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("sin permiso para crear enlaces simbólicos")
    code, _, _ = _purgar("--confirmar")
    assert code == 2
    assert victim.exists()


def test_purgar_help(workspace: Path) -> None:
    result = runner.invoke(app, ["purgar", "--help"])
    assert result.exit_code == 0
    assert "--confirmar" in result.stdout
    assert "--fuente" in result.stdout


def test_partial_purge_exits_1_and_logs_failed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = _touch(workspace / "output" / f"resultado_{OLD_RUN}.xlsx")
    free = _touch(workspace / "output" / f"resultado_{OLD_RUN}_1.xlsx")
    original = Path.unlink

    def fake_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == locked.name:
            raise PermissionError
        original(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    code, out, err = _purgar("--confirmar")
    assert code == 1
    assert locked.exists()
    assert not free.exists()
    assert "No se pudieron eliminar 1 archivos" in err
    assert OLD_RUN not in out + err
    assert str(workspace) not in out + err
    (event,) = _maintenance_events(workspace, skip=set())
    counts = event["purge_counts"]
    assert isinstance(counts, dict)
    assert counts["failed"] == 1
    assert counts["deleted"] == 1


def test_fuente_reports_orphans_and_does_not_delete_them(workspace: Path) -> None:
    orphan = _touch(workspace / "output" / f"resultado_{PORTAL_RUN}.xlsx", hours_old=1)
    code, out, _ = _purgar("--fuente", "PORTAL_DIAN_C1", "--confirmar")
    assert code == 0
    assert orphan.exists()
    assert "1 archivos de ejecuciones sin log de fuente: revise manualmente." in out
    (event,) = _maintenance_events(workspace, skip=set())
    counts = event["purge_counts"]
    assert isinstance(counts, dict)
    assert counts["unknown_source"] == 1
    assert counts["deleted"] == 0


def test_fuente_skips_recently_modified_files(workspace: Path) -> None:
    portal_log = _run_started(workspace / "logs" / f"run_{PORTAL_RUN}.jsonl", "PORTAL_DIAN_C1")
    busy = _touch(workspace / "output" / f"resultado_{PORTAL_RUN}.xlsx")  # recién modificado
    code, _, _ = _purgar("--fuente", "PORTAL_DIAN_C1", "--confirmar")
    assert code == 0
    assert busy.exists()
    assert not portal_log.exists()


def test_retention_below_365_warns(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_RETENTION_DAYS", "90")
    code, _, err = _purgar()
    assert code == 0
    assert "menor que la exigida por RN-06" in err


def test_default_retention_does_not_warn(workspace: Path) -> None:
    _, _, err = _purgar()
    assert "RN-06" not in err
