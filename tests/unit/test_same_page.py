"""`_same_page` ignora parámetros de ruta como `;jsessionid=...` (pendiente T-38 -> T-49)."""

import pytest

from rut_checker.adapters.dian_portal.detection import _same_page

BASE = "https://portal.dian.gov.co/Aplicacion/Formulario.faces"


@pytest.mark.parametrize(
    "other",
    [
        BASE,
        BASE + "/",
        BASE + ";jsessionid=ABC123",
        BASE + ";jsessionid=ABC123?x=1#frag",
        "HTTPS://PORTAL.DIAN.GOV.CO/Aplicacion;jsessionid=1/Formulario.faces",
    ],
)
def test_same_page_ignores_path_parameters_query_and_slash(other: str) -> None:
    assert _same_page(BASE, other)
    assert _same_page(other, BASE)


@pytest.mark.parametrize(
    "other",
    [
        "https://portal.dian.gov.co/Aplicacion/Otra.faces;jsessionid=ABC",
        "https://portal.dian.gov.co/img/Mantenimiento-Consulta-RUT.jpg",
        "http://portal.dian.gov.co/Aplicacion/Formulario.faces",
        "https://otro.dian.gov.co/Aplicacion/Formulario.faces",
    ],
)
def test_same_page_still_detects_other_pages(other: str) -> None:
    assert not _same_page(BASE, other)
