"""Pruebas de los catálogos QueryStatus y SourceKind."""

import re
from pathlib import Path

from rut_checker.domain.status import QueryStatus, SourceKind

CATALOG = Path(__file__).resolve().parents[2] / "specs" / "excepciones.md"
NOT_IMPLEMENTED = {"ERROR_ALMACENAMIENTO"}  # No hay BD (ARQUITECTURA §12)


def _catalog_statuses() -> set[str]:
    rows = re.findall(r"^\|\s*`([A-Z_]+)`\s*\|", CATALOG.read_text(encoding="utf-8"), re.MULTILINE)
    return set(rows)


def test_catalog_matches_excepciones_md() -> None:
    catalog = _catalog_statuses()
    assert catalog >= NOT_IMPLEMENTED
    expected = catalog - NOT_IMPLEMENTED
    assert len(expected) >= 12, "no se pudo parsear el catálogo"
    assert {s.value for s in QueryStatus} == expected
    assert QueryStatus.VALIDADA_COPIA_RUT in QueryStatus


def test_values_equal_names() -> None:
    assert all(s.value == s.name for s in QueryStatus)
    assert all(s.value == s.name for s in SourceKind)


def test_source_kind_catalog() -> None:
    assert {s.value for s in SourceKind} == {
        "PORTAL_DIAN_C1",
        "COPIA_RUT_TERCERO",
        "CONTINGENCIA_MANUAL",
        "SIN_CONSULTA",
        "FAKE",
    }


def test_enums_are_str() -> None:
    assert f"{QueryStatus.EXITOSA}" == "EXITOSA"
    assert SourceKind.SIN_CONSULTA == "SIN_CONSULTA"
