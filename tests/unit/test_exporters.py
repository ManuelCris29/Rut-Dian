"""Pruebas del exportador Excel/JSON (T-46). Solo identificaciones de la lista blanca."""

import csv
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from rut_checker.domain.errors import ExportError, UnsafePathError, UnsafePathReason
from rut_checker.domain.models import (
    IdentificationInput,
    InputRow,
    QueryOutcome,
    RutResult,
)
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.io import exporters
from rut_checker.io.exporters import (
    COLUMNS,
    ExportKind,
    ExportReport,
    export_excel,
    export_json_backup,
    neutralize_cell,
)
from rut_checker.io.flat_exporters import export_csv, export_json

BOGOTA = timezone(timedelta(hours=-5))
WHEN = datetime(2026, 10, 9, 8, 30, tzinfo=BOGOTA)
FORMULA = '=HYPERLINK("http://x","clic")'
ID_ONE = "1000000001"
ID_TWO = "1000000002"
# Valores no incluidos en la lista blanca se arman en tiempo de ejecución.
NOT_WHITELISTED_PHONE = "300" + "1234" + "567"


def _ok(index: int = 0, ident: str = ID_ONE, dv: str | None = None) -> QueryOutcome:
    return QueryOutcome(
        row=InputRow(row_index=index, raw_identification=ident),
        identification=IdentificationInput(identification=ident, dv=dv),
        result=RutResult(
            status=QueryStatus.EXITOSA,
            source=SourceKind.FAKE,
            estado_rut="ACTIVO",
            name="PERSONA FICTICIA UNO",
        ),
        queried_at=WHEN,
        duration_ms=5,
    )


def _invalid(
    raw: str | int | float | None,
    raw_dv: str | None = None,
    raw_note: str | None = None,
    observation: str = "Número inválido: contiene caracteres no numéricos",
) -> QueryOutcome:
    return QueryOutcome(
        row=InputRow(row_index=1, raw_identification=raw, raw_dv=raw_dv, raw_note=raw_note),
        identification=None,
        result=RutResult(
            status=QueryStatus.ENTRADA_INVALIDA,
            source=SourceKind.SIN_CONSULTA,
            observation=observation,
        ),
        queried_at=WHEN,
        duration_ms=0,
    )


def _xlsx(outcomes: list[QueryOutcome], tmp_path: Path, name: str = "r.xlsx") -> Path:
    report = export_excel(outcomes, tmp_path / name, output_dir=tmp_path)
    assert report.kind is ExportKind.XLSX
    return report.path


def _read(path: Path) -> list[list[object]]:
    wb = load_workbook(path)
    assert wb.sheetnames == ["resultado"]
    return [list(r) for r in wb["resultado"].iter_rows(values_only=True)]


def test_one_row_per_input_with_spec_columns(tmp_path: Path) -> None:
    outcomes = [_ok(0), _invalid("12A45"), _ok(2, ID_TWO, dv="3")]
    rows = _read(_xlsx(outcomes, tmp_path, "resultado_x.xlsx"))
    assert tuple(rows[0]) == COLUMNS
    assert list(COLUMNS) == [
        "identificacion",
        "dv",
        "nombre_o_razon_social",
        "estado_rut",
        "fecha_consulta",
        "fuente",
        "estado_consulta",
        "observacion",
    ]
    assert len(rows) == 4
    assert [r[0] for r in rows[1:]] == [ID_ONE, "12A45", ID_TWO]
    assert rows[1][2:4] == ["PERSONA FICTICIA UNO", "ACTIVO"]
    assert rows[3][1] == "3"
    assert rows[2][6] == "ENTRADA_INVALIDA"


def test_every_row_has_source_and_date(tmp_path: Path) -> None:
    rows = _read(_xlsx([_ok(0), _invalid("12A45")], tmp_path))
    for row in rows[1:]:
        assert row[5]
        assert row[4] == "2026-10-09T08:30:00-05:00"
    assert rows[1][5] == "FAKE"
    assert rows[2][5] == "SIN_CONSULTA"


def test_identificacion_written_as_text(tmp_path: Path) -> None:
    outcomes = [_ok(0), _invalid(int(ID_ONE)), _invalid(float(ID_TWO))]
    ws = load_workbook(_xlsx(outcomes, tmp_path))["resultado"]
    for row in (2, 3, 4):
        cell = ws.cell(row=row, column=1)
        assert cell.data_type == "s"
        assert isinstance(cell.value, str)
    assert ws["A3"].value == ID_ONE
    assert ws["A4"].value == ID_TWO


def _outcome_with_text(value: str) -> QueryOutcome:
    return QueryOutcome(
        row=InputRow(row_index=0, raw_identification=ID_ONE),
        identification=IdentificationInput(identification=ID_ONE),
        result=RutResult(
            status=QueryStatus.EXITOSA,
            source=SourceKind.FAKE,
            estado_rut=value,
            name=value,
            observation=value,
        ),
        queried_at=WHEN,
        duration_ms=1,
    )


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_formula_like_values_are_neutralized(prefix: str, tmp_path: Path) -> None:
    value = f"{prefix}1+1"
    assert neutralize_cell(value) == "'" + value
    ws = load_workbook(_xlsx([_outcome_with_text(value)], tmp_path))["resultado"]
    for col in (3, 4, 8):
        cell = ws.cell(row=2, column=col)
        assert cell.data_type == "s"
        # El XML normaliza CR a LF al releer; lo relevante es el apostrofo inicial.
        assert cell.value == ("'" + value).replace(chr(13), chr(10))


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_json_backup_neutralizes_the_six_prefixes(prefix: str, tmp_path: Path) -> None:
    value = f"{prefix}1+1"
    path = export_json_backup([_outcome_with_text(value)], tmp_path, "resultado_run")
    record = json.loads(path.read_text(encoding="utf-8"))[0]
    for column in ("nombre_o_razon_social", "estado_rut", "observacion"):
        assert record[column] == "'" + value


def test_neutralize_leaves_safe_text_untouched() -> None:
    assert neutralize_cell("ACTIVO") == "ACTIVO"
    assert neutralize_cell("") == ""


def test_formula_in_raw_identification_of_invalid_row_is_neutralized(tmp_path: Path) -> None:
    ws = load_workbook(_xlsx([_invalid(FORMULA, raw_dv=FORMULA)], tmp_path))["resultado"]
    for ref in ("A2", "B2"):
        assert ws[ref].data_type == "s"
        assert ws[ref].value == "'" + FORMULA


ILLEGAL_CHARS = ["\x00", "\x07", "\x1f", "￾", "￿", "\ud800", "\udfff"]


@pytest.mark.parametrize("char", ILLEGAL_CHARS)
def test_control_chars_do_not_break_export_nor_leak(char: str, tmp_path: Path) -> None:
    dirty = ID_ONE[:4] + char + ID_ONE[4:]
    outcome = _invalid(dirty, raw_dv=char, raw_note="a" + char + "b")
    expected = ID_ONE[:4] + "�" + ID_ONE[4:]
    # El .xlsx debe poder releerse (un XML invalido no es un exito).
    ws = load_workbook(_xlsx([outcome], tmp_path))["resultado"]
    assert ws["A2"].value == expected
    assert ws["B2"].value == "�"
    # El JSON debe codificarse y releerse (un surrogate suelto lo romperia).
    path = export_json_backup([outcome], tmp_path, "resultado_run")
    record = json.loads(path.read_text(encoding="utf-8"))[0]
    assert record["identificacion"] == expected
    assert record["dv"] == "�"


def test_illegal_character_error_is_translated_without_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exporters, "_sanitize", lambda value: value)
    dirty = ID_ONE[:4] + "\x00" + ID_ONE[4:]
    report = export_excel([_invalid(dirty)], tmp_path / "r.xlsx", output_dir=tmp_path)
    assert report.kind is ExportKind.JSON_BACKUP
    assert not (tmp_path / "r.xlsx").exists()
    assert not (tmp_path / "r_1.xlsx").exists()


def test_invalid_row_note_is_never_exported(tmp_path: Path) -> None:
    note = f"llamar al {NOT_WHITELISTED_PHONE} hoy"
    outcome = _invalid("12A45", raw_note=note)
    rows = _read(_xlsx([outcome], tmp_path))
    assert rows[1][7] == "Número inválido: contiene caracteres no numéricos"
    path = export_json_backup([outcome], tmp_path, "resultado_run")
    content = path.read_text(encoding="utf-8")
    assert "llamar" not in content
    assert NOT_WHITELISTED_PHONE not in content
    assert "llamar" not in str(rows)


def _lock_workbook_save(monkeypatch: pytest.MonkeyPatch, fail_times: int) -> list[int]:
    original = Workbook.save
    calls: list[int] = []

    def _save(self: Workbook, filename: str | Path) -> None:
        calls.append(1)
        if len(calls) <= fail_times:
            raise PermissionError("bloqueado")
        original(self, filename)

    monkeypatch.setattr(Workbook, "save", _save)
    return calls


def test_locked_file_falls_back_then_json_in_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "resultado_run.xlsx"
    calls = _lock_workbook_save(monkeypatch, fail_times=2)
    outcomes = [_ok(0), _invalid("12A45", raw_dv="=1")]
    report = export_excel(outcomes, target, output_dir=tmp_path)
    assert len(calls) == 2
    assert report == ExportReport(path=tmp_path / "resultado_run.json", kind=ExportKind.JSON_BACKUP)
    data = json.loads(report.path.read_text(encoding="utf-8"))
    assert list(data[0]) == list(COLUMNS)
    assert data[0]["identificacion"] == ID_ONE
    assert data[1]["dv"] == "'=1"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["resultado_run.json"]


def test_alternative_name_is_used_when_first_attempt_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lock_workbook_save(monkeypatch, fail_times=1)
    report = export_excel([_ok(0)], tmp_path / "resultado_run.xlsx", output_dir=tmp_path)
    assert report == ExportReport(
        path=tmp_path / "resultado_run_1.xlsx", kind=ExportKind.XLSX_ALTERNATIVE
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["resultado_run_1.xlsx"]


def test_success_returns_xlsx_kind_and_leaves_no_temp_file(tmp_path: Path) -> None:
    report = export_excel([_ok(0)], tmp_path / "resultado_run.xlsx", output_dir=tmp_path)
    assert report == ExportReport(path=tmp_path / "resultado_run.xlsx", kind=ExportKind.XLSX)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["resultado_run.xlsx"]


def test_all_three_outputs_failing_raises_generic_export_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lock_workbook_save(monkeypatch, fail_times=2)
    # Un directorio con el nombre del JSON impide el reemplazo atomico.
    (tmp_path / "resultado_run.json").mkdir()
    with pytest.raises(ExportError) as info:
        export_excel([_ok(0)], tmp_path / "resultado_run.xlsx", output_dir=tmp_path)
    assert "bloqueado" not in str(info.value)
    assert ID_ONE not in str(info.value)
    assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]


def test_target_outside_output_dir_is_rejected(tmp_path: Path) -> None:
    out = tmp_path / "output"
    out.mkdir()
    with pytest.raises(UnsafePathError) as info:
        export_excel([_ok(0)], tmp_path / "otro.xlsx", output_dir=out)
    assert info.value.reason is UnsafePathReason.OUTSIDE_OUTPUT_DIR
    assert not (tmp_path / "otro.xlsx").exists()


def test_wrong_suffix_is_rejected_and_uppercase_is_accepted(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError) as info:
        export_excel([_ok(0)], tmp_path / "r.txt", output_dir=tmp_path)
    assert info.value.reason is UnsafePathReason.INVALID_PATH
    report = export_excel([_ok(0)], tmp_path / "R.XLSX", output_dir=tmp_path)
    assert report.kind is ExportKind.XLSX


@pytest.mark.parametrize("name", ["", "../x", "a/b", "..", "a\\b"])
def test_json_backup_rejects_unsafe_names(name: str, tmp_path: Path) -> None:
    out = tmp_path / "output"
    out.mkdir()
    with pytest.raises(UnsafePathError):
        export_json_backup([_ok(0)], out, name)
    assert list(out.iterdir()) == []
    assert not (tmp_path / "x.json").exists()


def test_json_backup_columns_only_and_utf8(tmp_path: Path) -> None:
    path = export_json_backup([_ok(0)], tmp_path, "resultado_run")
    assert path == tmp_path / "resultado_run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == [
        {
            "identificacion": ID_ONE,
            "dv": "",
            "nombre_o_razon_social": "PERSONA FICTICIA UNO",
            "estado_rut": "ACTIVO",
            "fecha_consulta": "2026-10-09T08:30:00-05:00",
            "fuente": "FAKE",
            "estado_consulta": "EXITOSA",
            "observacion": "",
        }
    ]


def test_json_backup_failure_raises_generic_export_error(tmp_path: Path) -> None:
    missing = tmp_path / "no_existe" / "sub"
    with pytest.raises(ExportError) as info:
        export_json_backup([_ok(0)], missing, "resultado_run")
    assert str(missing) not in str(info.value)


def test_utc_datetime_is_converted_to_bogota(tmp_path: Path) -> None:
    base = _ok(0)
    utc_outcome = QueryOutcome(
        row=base.row,
        identification=base.identification,
        result=base.result,
        queried_at=datetime(2026, 10, 9, 13, 30, tzinfo=UTC),
        duration_ms=1,
    )
    rows = _read(_xlsx([utc_outcome], tmp_path))
    assert rows[1][4] == "2026-10-09T08:30:00-05:00"


def test_existing_unlocked_destination_is_never_overwritten(tmp_path: Path) -> None:
    # Sin bloqueo alguno: un destino existente se trata como fallo y no deja temporales.
    previous = tmp_path / "resultado_run.xlsx"
    previous.write_bytes(b"previo")
    report = export_excel([_ok(0)], previous, output_dir=tmp_path)
    assert previous.read_bytes() == b"previo"
    assert report == ExportReport(
        path=tmp_path / "resultado_run_1.xlsx", kind=ExportKind.XLSX_ALTERNATIVE
    )
    assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]


# --- T-47: CSV (neutralización por primer carácter visible) -----------------------------------

FULLWIDTH = [chr(code) for code in (0xFF1D, 0xFF0B, 0xFF0D, 0xFF20)]  # = + - @ de ancho completo
DANGEROUS_FIRST = ["=", "+", "-", "@", "\t", "\r", *FULLWIDTH, "|"]
ZERO_WIDTH_SPACE, BOM, NBSP = chr(0x200B), chr(0xFEFF), chr(0xA0)
INVISIBLE_PREFIXES = ["", " ", "  ", ZERO_WIDTH_SPACE, BOM, NBSP, f" {ZERO_WIDTH_SPACE}{BOM} "]


def _csv_records(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


@pytest.mark.parametrize("invisible", INVISIBLE_PREFIXES)
@pytest.mark.parametrize("danger", DANGEROUS_FIRST)
def test_csv_has_spec_columns_and_neutralized_cells(
    danger: str, invisible: str, tmp_path: Path
) -> None:
    value = f"{invisible}{danger}1+1"
    report = export_csv(
        [_ok(0), _outcome_with_text(value)], tmp_path / "r.csv", output_dir=tmp_path
    )
    assert report.kind is ExportKind.CSV
    raw = report.path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM UTF-8 para Excel en Windows
    records = _csv_records(report.path)
    assert tuple(records[0]) == COLUMNS
    assert len(records) == 3
    assert records[1][0] == ID_ONE
    for column in (2, 3, 7):
        # CR y LF se aplanan a espacio: un CR inicial ya no queda al comienzo de línea.
        flat = value.replace(chr(13), " ").replace(chr(10), " ")
        assert records[2][column] == (flat if danger == chr(13) else "'" + value)


@pytest.mark.parametrize("text", ["ACTIVO", " ACTIVO", "1+1", "a=b", "x-y", "N-1", "ñandú"])
def test_csv_leaves_safe_text_untouched(text: str, tmp_path: Path) -> None:
    report = export_csv([_outcome_with_text(text)], tmp_path / "r.csv", output_dir=tmp_path)
    assert _csv_records(report.path)[1][2] == text


def test_csv_quotes_commas_and_quotes_and_flattens_newlines(tmp_path: Path) -> None:
    value = 'a,"b"\nc'
    report = export_csv([_outcome_with_text(value)], tmp_path / "r.csv", output_dir=tmp_path)
    assert _csv_records(report.path)[1][3] == value.replace(chr(10), " ")


@pytest.mark.parametrize("raw", ["-" + ID_ONE, "+" + ID_ONE, "=" + ID_ONE])
def test_csv_signed_identifier_is_neutralized_and_does_not_break(raw: str, tmp_path: Path) -> None:
    report = export_csv([_invalid(raw, raw_dv="-1")], tmp_path / "r.csv", output_dir=tmp_path)
    row = _csv_records(report.path)[1]
    assert row[0] == "'" + raw
    assert row[1] == "'-1"


def test_csv_invalid_row_note_is_never_exported(tmp_path: Path) -> None:
    outcome = _invalid("12A45", raw_note=f"llamar al {NOT_WHITELISTED_PHONE} hoy")
    report = export_csv([outcome], tmp_path / "r.csv", output_dir=tmp_path)
    assert "llamar" not in report.path.read_text(encoding="utf-8")


def test_csv_replaces_illegal_characters(tmp_path: Path) -> None:
    dirty = ID_ONE[:4] + "\x00" + ID_ONE[4:]
    report = export_csv([_invalid(dirty)], tmp_path / "r.csv", output_dir=tmp_path)
    assert _csv_records(report.path)[1][0] == ID_ONE[:4] + "�" + ID_ONE[4:]


def test_csv_never_overwrites_and_falls_back_to_alternative(tmp_path: Path) -> None:
    previous = tmp_path / "r.csv"
    previous.write_bytes(b"previo")
    report = export_csv([_ok(0)], previous, output_dir=tmp_path)
    assert previous.read_bytes() == b"previo"
    assert report == ExportReport(tmp_path / "r_1.csv", ExportKind.CSV_ALTERNATIVE)
    assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]


def test_csv_falls_back_to_json_backup_when_both_csv_names_fail(tmp_path: Path) -> None:
    (tmp_path / "r.csv").write_bytes(b"1")
    (tmp_path / "r_1.csv").write_bytes(b"2")
    report = export_csv([_ok(0)], tmp_path / "r.csv", output_dir=tmp_path)
    assert report == ExportReport(tmp_path / "r.json", ExportKind.JSON_BACKUP)
    assert json.loads(report.path.read_text(encoding="utf-8"))[0]["identificacion"] == ID_ONE


def test_csv_all_destinations_failing_raises_generic_export_error(tmp_path: Path) -> None:
    for name in ("r.csv", "r_1.csv", "r.json"):
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(ExportError) as info:
        export_csv([_ok(0)], tmp_path / "r.csv", output_dir=tmp_path)
    assert ID_ONE not in str(info.value)


def test_csv_rejects_outside_dir_and_wrong_suffix(tmp_path: Path) -> None:
    out = tmp_path / "output"
    out.mkdir()
    with pytest.raises(UnsafePathError) as outside:
        export_csv([_ok(0)], tmp_path / "otro.csv", output_dir=out)
    assert outside.value.reason is UnsafePathReason.OUTSIDE_OUTPUT_DIR
    with pytest.raises(UnsafePathError) as suffix:
        export_csv([_ok(0)], out / "r.xlsx", output_dir=out)
    assert suffix.value.reason is UnsafePathReason.INVALID_PATH
    assert list(out.iterdir()) == []


# --- T-47: JSON -------------------------------------------------------------------------------


def test_json_has_exactly_spec_keys_in_order_and_utf8(tmp_path: Path) -> None:
    report = export_json([_ok(0), _invalid("12A45")], tmp_path / "r.json", output_dir=tmp_path)
    assert report == ExportReport(tmp_path / "r.json", ExportKind.JSON)
    text = report.path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert [list(item) for item in data] == [list(COLUMNS)] * 2
    assert data[0]["identificacion"] == ID_ONE
    assert data[0]["fecha_consulta"] == "2026-10-09T08:30:00-05:00"
    assert data[1]["estado_consulta"] == "ENTRADA_INVALIDA"


def test_json_keeps_non_ascii_unescaped_and_does_not_neutralize(tmp_path: Path) -> None:
    outcome = _outcome_with_text("=ñandú")
    report = export_json([outcome], tmp_path / "r.json", output_dir=tmp_path)
    text = report.path.read_text(encoding="utf-8")
    assert "ñandú" in text
    assert json.loads(text)[0]["nombre_o_razon_social"] == "=ñandú"


def test_json_escapes_control_chars_and_replaces_illegal_ones(tmp_path: Path) -> None:
    outcome = _outcome_with_text("a\tb\nc\x00d\ud800")
    report = export_json([outcome], tmp_path / "r.json", output_dir=tmp_path)
    text = report.path.read_text(encoding="utf-8")
    assert "\t" not in text.replace("\n", "")  # el tabulador va escapado
    assert json.loads(text)[0]["nombre_o_razon_social"] == "a\tb\nc�d�"


def test_json_invalid_row_note_is_never_exported(tmp_path: Path) -> None:
    outcome = _invalid("12A45", raw_note=f"llamar al {NOT_WHITELISTED_PHONE} hoy")
    report = export_json([outcome], tmp_path / "r.json", output_dir=tmp_path)
    assert "llamar" not in report.path.read_text(encoding="utf-8")


def test_json_never_overwrites_uses_alternative_then_raises(tmp_path: Path) -> None:
    previous = tmp_path / "r.json"
    previous.write_bytes(b"previo")
    report = export_json([_ok(0)], previous, output_dir=tmp_path)
    assert previous.read_bytes() == b"previo"
    assert report == ExportReport(tmp_path / "r_1.json", ExportKind.JSON_ALTERNATIVE)
    with pytest.raises(ExportError):
        export_json([_ok(0)], previous, output_dir=tmp_path)


def test_json_rejects_outside_dir_and_wrong_suffix(tmp_path: Path) -> None:
    out = tmp_path / "output"
    out.mkdir()
    with pytest.raises(UnsafePathError):
        export_json([_ok(0)], tmp_path / "otro.json", output_dir=out)
    with pytest.raises(UnsafePathError):
        export_json([_ok(0)], out / "r.csv", output_dir=out)


def test_csv_no_physical_line_starts_with_a_formula(tmp_path: Path) -> None:
    """Los saltos de línea dentro de una celda se vuelven espacio (T-47, BAJA)."""
    report = export_csv(
        [_outcome_with_text("ab\ncd\r\n=1+1")], tmp_path / "r.csv", output_dir=tmp_path
    )
    assert _csv_records(report.path)[1][2] == "ab cd  =1+1"
    lines = report.path.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) == 2
    assert not any(line.startswith(("=", "+", "-", "@")) for line in lines)


IGNORABLES = [
    chr(c) for c in (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x180B, 0x180D, 0xFE00, 0xFE0F)
]


@pytest.mark.parametrize("ignorable", IGNORABLES)
def test_csv_skips_default_ignorable_characters_before_the_formula(
    ignorable: str, tmp_path: Path
) -> None:
    value = f"{ignorable}=1+1"
    report = export_csv([_outcome_with_text(value)], tmp_path / "r.csv", output_dir=tmp_path)
    assert _csv_records(report.path)[1][2] == "'" + value
