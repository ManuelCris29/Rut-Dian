"""Pruebas de la carga y validación de `selectors.yaml` (T-37, triple llave: llave 3).

Las pruebas del camino válido inyectan la raíz del proyecto con las funciones privadas
`_load_validated` y `_ensure_enabled`: la API pública (`load_selectors`, `ensure_portal_enabled`)
usa siempre la raíz fija del paquete y es la única que `build_service` puede invocar.
"""

import ast
import copy
import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from rut_checker.adapters.dian_portal import location as location_module
from rut_checker.adapters.dian_portal import selectors as selectors_module
from rut_checker.adapters.dian_portal.location import _find_project_root
from rut_checker.adapters.dian_portal.selectors import (
    MAX_SELECTORS_FILE_BYTES,
    RESERVED_SYNTHETIC_APPROVAL_REF,
    EnabledPortal,
    PortalSelectors,
    _check_ready,
    _ensure_enabled,
    _load_validated,
    _parse_file,
    enabled_portal_from_synthetic_fixture,
    ensure_portal_enabled,
    load_selectors,
)
from rut_checker.domain.errors import (
    SelectorsNotValidatedError,
    SelectorsReason,
    SourceNotEnabledError,
    SourceNotEnabledReason,
)
from rut_checker.infra.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_SELECTORS = REPO_ROOT / "config" / "selectors.yaml"
SYNTHETIC_SELECTORS = REPO_ROOT / "tests" / "fixtures" / "selectors_test.yaml"
APPROVAL_REF = "APR-20261009-1"
SNAPSHOT = "docs/investigacion/snapshot-neutro.md"

# Documento completo y válido con valores neutros (no representa el portal de la DIAN).
VALID: dict[str, object] = {
    "validated": True,
    "version": "neutra-1",
    "approval_ref": APPROVAL_REF,
    "source_snapshot": SNAPSHOT,
    "form": {
        "id_input": {"strategy": "testid", "value": "campo-neutro"},
        "submit_button": {"strategy": "role", "role": "button", "name": "enviar-neutro"},
    },
    "result": {
        "status": {"strategy": "testid", "value": "estado-neutro"},
        "name": {"strategy": "testid", "value": "nombre-neutro", "required": False},
        "no_result_msg": {"strategy": "text", "value": "sin-resultado-neutro"},
    },
    "detection": {
        "maintenance_url_markers": ["mantenimiento-neutro"],
        "challenge_markers": [{"strategy": "testid", "value": "desafio-neutro"}],
        "block_markers": [{"strategy": "testid", "value": "bloqueo-neutro"}],
    },
}


def _section(name: str) -> dict[str, object]:
    section = copy.deepcopy(VALID[name])
    assert isinstance(section, dict)
    return section


def _write(root: Path, data: object) -> Path:
    """Escribe `data` en `root/config/selectors.yaml` con el snapshot referenciado presente."""
    snapshot = root / SNAPSHOT
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("# snapshot neutro de prueba\n", encoding="utf-8")
    path = root / "config" / "selectors.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _doc(**overrides: object) -> dict[str, object]:
    data = copy.deepcopy(VALID)
    data.update(overrides)
    return data


def _detection(**changes: object) -> dict[str, object]:
    detection = _section("detection")
    detection.update(changes)
    return detection


def _form(**changes: object) -> dict[str, object]:
    form = _section("form")
    form.update(changes)
    return form


def _result(**changes: object) -> dict[str, object]:
    result = _section("result")
    result.update(changes)
    return result


def _fails(path: Path, reason: SelectorsReason, ref: str = APPROVAL_REF) -> None:
    """La raíz inyectada es la del propio árbol temporal (`<raíz>/config/selectors.yaml`)."""
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(path, ref, path.parent.parent)
    assert info.value.reason is reason
    assert str(path) not in str(info.value)


def test_valid_document_loads(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    selectors = _load_validated(path, APPROVAL_REF, tmp_path)
    assert isinstance(selectors, PortalSelectors)
    assert selectors.approval_ref == APPROVAL_REF
    assert selectors.result.name is not None


# --- B-1: la raíz está anclada al paquete, no al archivo ------------------------------------


def test_repo_selectors_are_not_validated() -> None:
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(REPO_SELECTORS, APPROVAL_REF)
    assert info.value.reason is SelectorsReason.NOT_VALIDATED


def test_project_root_is_found_from_the_package() -> None:
    assert _find_project_root(Path(selectors_module.__file__)) == REPO_ROOT


def test_project_root_requires_rut_checker_pyproject(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert _find_project_root(deep / "x.py") is None
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "otro"\n', encoding="utf-8")
    assert _find_project_root(deep / "x.py") is None
    (tmp_path / "pyproject.toml").write_text("esto no es toml [", encoding="utf-8")
    assert _find_project_root(deep / "x.py") is None
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "rut-checker"\n', encoding="utf-8")
    assert _find_project_root(deep / "x.py") == tmp_path.resolve()


def test_installed_outside_a_project_cannot_enable_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(location_module, "_find_project_root", lambda _start: None)
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(REPO_SELECTORS, APPROVAL_REF)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_file_copied_outside_the_repo_is_rejected(tmp_path: Path) -> None:
    """B-1: el fixture copiado fuera del repo con `synthetic: false` y un docs/ de relleno."""
    text = SYNTHETIC_SELECTORS.read_text(encoding="utf-8").replace(
        "synthetic: true", "synthetic: false"
    )
    path = _write(tmp_path, VALID)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(path, RESERVED_SYNTHETIC_APPROVAL_REF)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT
    # Aun con raíz inyectada, la referencia reservada se rechaza explícitamente.
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(path, RESERVED_SYNTHETIC_APPROVAL_REF, tmp_path)
    assert info.value.reason is SelectorsReason.SYNTHETIC


def test_valid_looking_copy_outside_the_repo_is_rejected_by_public_loader(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(path, APPROVAL_REF)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_other_file_inside_the_root_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    other = path.with_name("otro.yaml")
    shutil.copy(path, other)
    _fails(other, SelectorsReason.OUTSIDE_PROJECT)


def test_relative_path_from_another_cwd_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, VALID)
    elsewhere = tmp_path / "otro-cwd"
    _write(elsewhere, VALID)  # `config/selectors.yaml` relativo al cwd, pero fuera de la raíz
    monkeypatch.chdir(elsewhere)
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(Path("config/selectors.yaml"), APPROVAL_REF, tmp_path)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT
    # Con la ruta correcta el cwd no importa.
    monkeypatch.chdir(tmp_path.parent)
    assert _load_validated(path, APPROVAL_REF, tmp_path)


def test_real_config_is_reached_from_any_cwd_with_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(REPO_SELECTORS, APPROVAL_REF)
    assert info.value.reason is SelectorsReason.NOT_VALIDATED
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(Path("config/selectors.yaml"), APPROVAL_REF)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_file_symlink_to_real_file_is_rejected(tmp_path: Path) -> None:
    real = _write(tmp_path / "real", VALID)
    link = tmp_path / "root" / "config" / "selectors.yaml"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("no se pueden crear enlaces simbólicos en este entorno")
    shutil.copytree(tmp_path / "real" / "docs", tmp_path / "root" / "docs")
    _fails(link, SelectorsReason.OUTSIDE_PROJECT)


def test_config_dir_symlink_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "real", VALID)
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "config").symlink_to(tmp_path / "real" / "config", target_is_directory=True)
    except OSError:
        pytest.skip("no se pueden crear enlaces simbólicos en este entorno")
    shutil.copytree(tmp_path / "real" / "docs", root / "docs")
    _fails(root / "config" / "selectors.yaml", SelectorsReason.OUTSIDE_PROJECT)


@pytest.mark.skipif(os.name != "nt", reason="las junctions solo existen en Windows")
def test_config_dir_junction_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "real", VALID)
    root = tmp_path / "root"
    root.mkdir()
    # `_winapi.CreateJunction` es API privada, pero es la única forma de crear una junction sin
    # privilegios de administrador (os.symlink los exige) desde la biblioteca estándar.
    winapi = importlib.import_module("_winapi")
    winapi.CreateJunction(str(tmp_path / "real" / "config"), str(root / "config"))
    shutil.copytree(tmp_path / "real" / "docs", root / "docs")
    _fails(root / "config" / "selectors.yaml", SelectorsReason.OUTSIDE_PROJECT)


def test_snapshot_is_searched_under_the_fixed_root(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    (tmp_path / SNAPSHOT).unlink()
    _fails(path, SelectorsReason.SNAPSHOT_MISSING)
    # Un snapshot de relleno en otra carpeta (junto al archivo) no cuenta.
    decoy = path.parent / SNAPSHOT
    decoy.parent.mkdir(parents=True)
    decoy.write_text("relleno", encoding="utf-8")
    _fails(path, SelectorsReason.SNAPSHOT_MISSING)


# --- Contenido -------------------------------------------------------------------------------


def test_repo_selectors_contain_only_placeholders_and_no_real_values() -> None:
    raw = yaml.safe_load(REPO_SELECTORS.read_text(encoding="utf-8"))
    assert raw["validated"] is False
    assert raw["approval_ref"] == ""
    assert raw["source_snapshot"] == ""
    text = REPO_SELECTORS.read_text(encoding="utf-8").lower()
    for forbidden in ("turnstile", "recaptcha", "cloudflare", "muisca", "faces"):
        assert forbidden not in text


@pytest.mark.parametrize(
    "document",
    [
        _doc(version="PENDIENTE"),
        _doc(form=_form(id_input={"strategy": "label", "value": "PENDIENTE"})),
        _doc(form=_form(submit_button={"strategy": "role", "role": "button", "name": "PENDIENTE"})),
        _doc(detection=_detection(maintenance_url_markers=["PENDIENTE"])),
        _doc(detection=_detection(challenge_markers=[{"strategy": "css", "value": "PENDIENTE"}])),
        _doc(version="pendiente de snapshot"),
        _doc(version="PENDIENTE_x"),
        _doc(version="pen\u200bdiente"),  # carácter de formato (Cf) intercalado
        _doc(
            version="\uff30\uff25\uff2e\uff24\uff29\uff25\uff2e\uff34\uff25"
        ),  # anchos completos, NFKC
    ],
    ids=[
        "version",
        "label",
        "role-name",
        "maintenance-marker",
        "challenge-marker",
        "lowercase",
        "underscore",
        "zero-width",
        "fullwidth",
    ],
)
def test_placeholder_in_required_selector_fails(tmp_path: Path, document: object) -> None:
    _fails(_write(tmp_path, document), SelectorsReason.PLACEHOLDER)


@pytest.mark.parametrize("word", ["independiente", "Dependiente", "pendientes"])
def test_placeholder_has_no_false_positives_on_longer_words(tmp_path: Path, word: str) -> None:
    path = _write(tmp_path, _doc(version=word))
    assert _load_validated(path, APPROVAL_REF, tmp_path)


def test_synthetic_file_is_rejected_by_production_loader(tmp_path: Path) -> None:
    # Documento completo y válido salvo `synthetic: true`: el rechazo es solo por eso (D-4).
    _fails(_write(tmp_path, _doc(synthetic=True)), SelectorsReason.SYNTHETIC)


def test_repo_synthetic_fixture_is_synthetic_and_rejected_by_check_ready(tmp_path: Path) -> None:
    parsed = _parse_file(SYNTHETIC_SELECTORS)
    assert parsed.synthetic is True
    with pytest.raises(SelectorsNotValidatedError) as info:
        _check_ready(parsed, parsed.approval_ref, tmp_path)
    assert info.value.reason is SelectorsReason.SYNTHETIC
    assert SYNTHETIC_SELECTORS.read_text(encoding="utf-8").startswith(
        "# SINTÉTICO — no representa el portal de la DIAN"
    )
    # Y el cargador público no lo acepta por estar fuera de config/selectors.yaml.
    with pytest.raises(SelectorsNotValidatedError) as info:
        load_selectors(SYNTHETIC_SELECTORS, parsed.approval_ref)
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_synthetic_fixture_has_reserved_ref_and_nonexistent_snapshot() -> None:
    parsed = _parse_file(SYNTHETIC_SELECTORS)
    assert parsed.approval_ref == RESERVED_SYNTHETIC_APPROVAL_REF == "APR-19700101-0"
    assert parsed.source_snapshot == "docs/investigacion/SINTETICO-no-existe.md"
    assert not (REPO_ROOT / parsed.source_snapshot).exists()


def test_reserved_approval_ref_is_rejected_even_if_everything_else_is_valid(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _doc(approval_ref=RESERVED_SYNTHETIC_APPROVAL_REF))
    _fails(path, SelectorsReason.SYNTHETIC, ref=RESERVED_SYNTHETIC_APPROVAL_REF)


def test_synthetic_fixture_uses_neutral_selectors_only() -> None:
    text = SYNTHETIC_SELECTORS.read_text(encoding="utf-8").lower()
    for forbidden in ("turnstile", "recaptcha", "cloudflare", "cf-", "g-recaptcha", "muisca"):
        assert forbidden not in text
    assert "-sintetico" in text


def test_approval_ref_mismatch_fails(tmp_path: Path) -> None:
    _fails(_write(tmp_path, VALID), SelectorsReason.APPROVAL_MISMATCH, ref="APR-20261009-2")


@pytest.mark.parametrize("ref", ["", "no-valido"])
def test_invalid_expected_approval_ref_has_its_own_reason(tmp_path: Path, ref: str) -> None:
    _fails(_write(tmp_path, VALID), SelectorsReason.INVALID_APPROVAL_REF, ref=ref)


def test_empty_file_approval_ref_fails(tmp_path: Path) -> None:
    _fails(_write(tmp_path, _doc(approval_ref="")), SelectorsReason.APPROVAL_MISMATCH)


def test_empty_challenge_markers_without_observed_none_fails(tmp_path: Path) -> None:
    data = _doc(detection=_detection(challenge_markers=[]))
    _fails(_write(tmp_path, data), SelectorsReason.CHALLENGE_MARKERS_MISSING)


def test_empty_block_markers_without_observed_none_fails(tmp_path: Path) -> None:
    data = _doc(detection=_detection(block_markers=[]))
    _fails(_write(tmp_path, data), SelectorsReason.BLOCK_MARKERS_MISSING)


def test_empty_markers_with_observed_none_and_evidence_load(tmp_path: Path) -> None:
    detection = _detection(
        challenge_markers=[],
        challenge_observed="none",
        challenge_evidence="05-analisis-tecnico.md §4: sin desafío observado",
        block_markers=[],
        block_observed="none",
        block_evidence="05-analisis-tecnico.md §4: sin bloqueo observado",
    )
    path = _write(tmp_path, _doc(detection=detection))
    assert _load_validated(path, APPROVAL_REF, tmp_path)


@pytest.mark.parametrize("evidence", ["", "   "])
def test_observed_none_without_evidence_fails(tmp_path: Path, evidence: str) -> None:
    detection = _detection(
        challenge_markers=[], challenge_observed="none", challenge_evidence=evidence
    )
    _fails(_write(tmp_path, _doc(detection=detection)), SelectorsReason.CHALLENGE_MARKERS_MISSING)


def test_observed_none_with_placeholder_evidence_fails(tmp_path: Path) -> None:
    detection = _detection(
        block_markers=[], block_observed="none", block_evidence="PENDIENTE de snapshot"
    )
    _fails(_write(tmp_path, _doc(detection=detection)), SelectorsReason.PLACEHOLDER)


def test_observed_none_with_markers_is_contradictory(tmp_path: Path) -> None:
    detection = _detection(challenge_observed="none", challenge_evidence="evidencia")
    _fails(_write(tmp_path, _doc(detection=detection)), SelectorsReason.INVALID_STRUCTURE)


@pytest.mark.parametrize("markers", [[], [""], ["  "]])
def test_empty_maintenance_markers_fails(tmp_path: Path, markers: list[str]) -> None:
    data = _doc(detection=_detection(maintenance_url_markers=markers))
    _fails(_write(tmp_path, data), SelectorsReason.MAINTENANCE_MARKERS_EMPTY)


def test_missing_snapshot_file_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    (tmp_path / SNAPSHOT).unlink()
    _fails(path, SelectorsReason.SNAPSHOT_MISSING)


@pytest.mark.parametrize(
    "snapshot", ["../fuera.md", "/etc/passwd", "docs/otra/archivo.md", "docs/investigacion/../x"]
)
def test_snapshot_must_live_in_docs_investigacion(tmp_path: Path, snapshot: str) -> None:
    path = _write(tmp_path, _doc(source_snapshot=snapshot))
    (tmp_path / "fuera.md").write_text("x", encoding="utf-8")
    _fails(path, SelectorsReason.SNAPSHOT_MISSING)


# --- M-2: el formulario y el resultado no pueden apuntar al desafío --------------------------


@pytest.mark.parametrize(
    "term",
    [
        "turnstile",
        "TURNSTILE",
        "challenges.cloudflare",
        "cf-chl",
        "captcha",
        "ReCaptcha",
        "hCaptcha",
        "cf_chl",
        "cdn-cgi",
        "cloudflare",
        "challenge",
        "geetest",
        "arkose",
    ],
)
@pytest.mark.parametrize("where", ["form-value", "form-name", "result-value"])
def test_forbidden_target_in_form_or_result_fails(tmp_path: Path, term: str, where: str) -> None:
    if where == "form-value":
        document = _doc(form=_form(id_input={"strategy": "css", "value": f"#{term}-x"}))
    elif where == "form-name":
        document = _doc(
            form=_form(submit_button={"strategy": "role", "role": "button", "name": term})
        )
    else:
        document = _doc(result=_result(status={"strategy": "css", "value": f"div.{term}"}))
    _fails(_write(tmp_path, document), SelectorsReason.FORBIDDEN_TARGET)


@pytest.mark.parametrize(
    "value",
    [
        "__cf_chl_tk",
        "/cdn-cgi/challenge-platform/h/b",
        "#challenge-form",
        "geetest_panel",
        "div.Arkose_Panel",
        "challenge_platform",
    ],
)
def test_forbidden_target_variants_with_underscores_and_paths(tmp_path: Path, value: str) -> None:
    document = _doc(form=_form(id_input={"strategy": "css", "value": value}))
    _fails(_write(tmp_path, document), SelectorsReason.FORBIDDEN_TARGET)


def test_forbidden_target_is_checked_after_nfkc_and_ignoring_format_chars(tmp_path: Path) -> None:
    value = "\uff54\uff55\uff52\uff4e\uff53\u200btile"  # anchos completos y carácter de formato
    document = _doc(form=_form(id_input={"strategy": "css", "value": value}))
    _fails(_write(tmp_path, document), SelectorsReason.FORBIDDEN_TARGET)


def test_challenge_markers_may_name_the_challenge(tmp_path: Path) -> None:
    detection = _detection(challenge_markers=[{"strategy": "css", "value": "caja-captcha"}])
    path = _write(tmp_path, _doc(detection=detection))
    assert _load_validated(path, APPROVAL_REF, tmp_path)


# --- Estructura, YAML y mensajes -------------------------------------------------------------


def test_validated_must_be_a_real_boolean(tmp_path: Path) -> None:
    _fails(_write(tmp_path, _doc(validated="true")), SelectorsReason.INVALID_STRUCTURE)


@pytest.mark.parametrize(
    "document",
    [
        _doc(unexpected_key=1),
        _doc(form={"id_input": _section("form")["id_input"]}),
        _doc(form=_form(id_input={"strategy": "xpath", "value": "x"})),
        _doc(form=_form(id_input={"strategy": "css"})),
        _doc(form=_form(id_input={"strategy": "role", "name": "x"})),
        ["no", "es", "un", "mapa"],
    ],
    ids=["extra-key", "missing-field", "bad-strategy", "css-no-value", "role-no-role", "not-a-map"],
)
def test_invalid_structure_fails(tmp_path: Path, document: object) -> None:
    _fails(_write(tmp_path, document), SelectorsReason.INVALID_STRUCTURE)


def test_validation_errors_do_not_echo_input_values() -> None:
    with pytest.raises(Exception) as info:  # noqa: PT011  # se inspecciona el texto del error
        PortalSelectors.model_validate({"validated": "valor-secreto-xyz"})
    assert "valor-secreto-xyz" not in str(info.value)


def test_unsafe_yaml_tag_is_not_executed(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text("validated: !!python/object/apply:os.getcwd []\n", encoding="utf-8")
    _fails(path, SelectorsReason.INVALID_YAML)


def test_malformed_yaml_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text("a: [1, 2\n", encoding="utf-8")
    _fails(path, SelectorsReason.INVALID_YAML)


@pytest.mark.parametrize(
    "extra",
    ["validated: false\n", "synthetic: true\nsynthetic: false\n"],
    ids=["validated-twice", "synthetic-twice"],
)
def test_duplicate_top_level_keys_are_rejected(tmp_path: Path, extra: str) -> None:
    path = _write(tmp_path, VALID)
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    _fails(path, SelectorsReason.DUPLICATE_KEY)


def test_duplicate_nested_keys_are_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text(
        "validated: true\nform:\n  id_input: {strategy: css, value: a, value: b}\n",
        encoding="utf-8",
    )
    _fails(path, SelectorsReason.DUPLICATE_KEY)


def test_anchors_and_aliases_are_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text(path.read_text(encoding="utf-8") + "x: &a 1\ny: *a\n", encoding="utf-8")
    _fails(path, SelectorsReason.INVALID_YAML)


def test_empty_yaml_file_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text("", encoding="utf-8")
    _fails(path, SelectorsReason.INVALID_STRUCTURE)


def test_non_utf8_file_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_bytes(b"\xff\xfe\x00\x00 invalido \x80")
    _fails(path, SelectorsReason.INVALID_YAML)


def test_oversized_file_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.write_text("# " + "x" * MAX_SELECTORS_FILE_BYTES + "\n", encoding="utf-8")
    _fails(path, SelectorsReason.TOO_LARGE)


def test_missing_and_directory_selectors_fail(tmp_path: Path) -> None:
    path = tmp_path / "config" / "selectors.yaml"
    _fails(path, SelectorsReason.UNREADABLE)
    path.mkdir(parents=True)
    _fails(path, SelectorsReason.UNREADABLE)


def test_error_messages_do_not_leak_values_or_paths(tmp_path: Path) -> None:
    data = _doc(version="valor-secreto-xyz", approval_ref="APR-20261009-9")
    path = _write(tmp_path / "carpeta-privada", data)
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(path, APPROVAL_REF, path.parent.parent)
    message = f"{info.value} {info.value!r}"
    assert "valor-secreto-xyz" not in message
    assert "carpeta-privada" not in message
    assert "APR-20261009-9" not in message


def test_missing_pyyaml_fails_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path, VALID)
    monkeypatch.setitem(sys.modules, "yaml", None)  # `import yaml` lanza ImportError
    _fails(path, SelectorsReason.YAML_UNAVAILABLE)


def test_dian_portal_modules_do_not_import_yaml_at_import_time() -> None:
    for module_path in Path(selectors_module.__file__).parent.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in tree.body:  # solo nivel de módulo: los imports perezosos viven en funciones
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.split(".")[0] == "yaml" for name in names), module_path.name


# --- ensure_portal_enabled: triple llave y puerta única --------------------------------------


def _settings(path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "portal_enabled": True,
        "portal_approval_ref": APPROVAL_REF,
        "selectors_path": path,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]  # dict de pruebas heterogéneo


def test_disabled_flag_raises_source_not_enabled(tmp_path: Path) -> None:
    settings = _settings(_write(tmp_path, VALID), portal_enabled=False)
    with pytest.raises(SourceNotEnabledError) as info:
        _ensure_enabled(settings, tmp_path)
    assert info.value.reason is SourceNotEnabledReason.FLAG_DISABLED


def test_missing_approval_ref_raises(tmp_path: Path) -> None:
    settings = _settings(_write(tmp_path, VALID), portal_approval_ref="")
    with pytest.raises(SourceNotEnabledError) as info:
        _ensure_enabled(settings, tmp_path)
    assert info.value.reason is SourceNotEnabledReason.MISSING_APPROVAL_REF


def test_headless_portal_is_not_enabled(tmp_path: Path) -> None:
    settings = _settings(_write(tmp_path, VALID), headless=True)
    with pytest.raises(SourceNotEnabledError) as info:
        _ensure_enabled(settings, tmp_path)
    assert info.value.reason is SourceNotEnabledReason.HEADLESS_NOT_ALLOWED


def test_invalid_portal_url_is_revalidated(tmp_path: Path) -> None:
    settings = _settings(_write(tmp_path, VALID))
    object.__setattr__(settings, "portal_url", "https://evil.example.com/")  # eludir frozen
    with pytest.raises(SourceNotEnabledError) as info:
        _ensure_enabled(settings, tmp_path)
    assert info.value.reason is SourceNotEnabledReason.INVALID_URL


def test_enabled_with_valid_selectors_returns_enabled_portal(tmp_path: Path) -> None:
    portal = _ensure_enabled(_settings(_write(tmp_path, VALID)), tmp_path)
    assert isinstance(portal, EnabledPortal)
    assert portal.selectors.approval_ref == APPROVAL_REF
    assert portal.synthetic is False


def test_enabled_portal_cannot_be_built_directly() -> None:
    selectors = PortalSelectors.model_validate(VALID)
    with pytest.raises(TypeError):
        EnabledPortal(selectors)  # type: ignore[call-arg]  # prueba intencional: falta el token
    with pytest.raises(TypeError):
        EnabledPortal(selectors, synthetic=False, _token=object())


def test_enabled_portal_is_immutable(tmp_path: Path) -> None:
    portal = _ensure_enabled(_settings(_write(tmp_path, VALID)), tmp_path)
    with pytest.raises(AttributeError):
        portal.synthetic = True  # type: ignore[misc]  # prueba intencional de inmutabilidad
    with pytest.raises(AttributeError):
        portal.extra = 1


def test_public_ensure_with_repo_selectors_always_fails() -> None:
    settings = _settings(REPO_SELECTORS)
    with pytest.raises(SelectorsNotValidatedError) as info:
        ensure_portal_enabled(settings)
    assert info.value.reason is SelectorsReason.NOT_VALIDATED


def test_public_ensure_rejects_a_valid_copy_outside_the_repo(tmp_path: Path) -> None:
    with pytest.raises(SelectorsNotValidatedError) as info:
        ensure_portal_enabled(_settings(_write(tmp_path, VALID)))
    assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_approval_ref_in_settings_must_match_file(tmp_path: Path) -> None:
    settings = _settings(_write(tmp_path, VALID), portal_approval_ref="APR-20261009-2")
    with pytest.raises(SelectorsNotValidatedError) as info:
        _ensure_enabled(settings, tmp_path)
    assert info.value.reason is SelectorsReason.APPROVAL_MISMATCH


# --- Vía explícita de pruebas con selectores sintéticos --------------------------------------


def test_synthetic_portal_is_explicit_and_marked() -> None:
    portal = enabled_portal_from_synthetic_fixture(SYNTHETIC_SELECTORS)
    assert portal.synthetic is True
    assert portal.selectors.synthetic is True


def test_synthetic_portal_rejects_files_outside_tests_fixtures(tmp_path: Path) -> None:
    for path in (REPO_SELECTORS, _write(tmp_path, _doc(synthetic=True))):
        with pytest.raises(SelectorsNotValidatedError) as info:
            enabled_portal_from_synthetic_fixture(path)
        assert info.value.reason is SelectorsReason.OUTSIDE_PROJECT


def test_synthetic_portal_rejects_a_non_synthetic_file_in_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(location_module, "_find_project_root", lambda _start: tmp_path)
    target = tmp_path / "tests" / "fixtures" / "otro.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump(VALID), encoding="utf-8")
    with pytest.raises(SelectorsNotValidatedError) as info:
        enabled_portal_from_synthetic_fixture(target)
    assert info.value.reason is SelectorsReason.NOT_SYNTHETIC
    assert not any(ch.isdigit() for ch in str(info.value))


def test_only_selectors_module_references_the_synthetic_entrypoint() -> None:
    src = REPO_ROOT / "src" / "rut_checker"
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path != Path(selectors_module.__file__)
        and any(
            name in path.read_text(encoding="utf-8")
            for name in (
                "enabled_portal_from_synthetic_fixture",
                "_load_validated",
                "_ensure_enabled",
                "_TOKEN",
                "EnabledPortal(",
            )
        )
    ]
    assert not offenders, f"build_service no puede usar las vías de prueba: {offenders}"


# --- M-1: sintaxis de selector que sale del DOM principal o cambia de motor -------------------

FORBIDDEN_SYNTAX = [
    "div >> internal:control=enter-frame",
    "iframe",
    "#mi-iframe",
    "div.marco-frame",
    "internal:role=button",
    "xpath=//div",
    "css=div",
    "text=algo",
    "id=algo",
    "nth=0",
    "_react=Foo",
    "_vue=Foo",
    "data-testid=algo",
    "//div[@id='x']",
    "../div",
    '"texto entrecomillado"',
    chr(0xFF49) + "frame",  # i de ancho completo + frame (NFKC)
]


@pytest.mark.parametrize("value", FORBIDDEN_SYNTAX)
@pytest.mark.parametrize("where", ["form", "result", "challenge", "block", "name", "role"])
def test_forbidden_selector_syntax_is_rejected_everywhere(
    tmp_path: Path, value: str, where: str
) -> None:
    spec: dict[str, object] = {"strategy": "css", "value": value}
    if where == "form":
        document = _doc(form=_form(id_input=spec))
    elif where == "result":
        document = _doc(result=_result(status=spec))
    elif where == "challenge":
        document = _doc(detection=_detection(challenge_markers=[spec]))
    elif where == "block":
        document = _doc(detection=_detection(block_markers=[spec]))
    elif where == "name":
        role_spec = {"strategy": "role", "role": "button", "name": value}
        document = _doc(form=_form(submit_button=role_spec))
    else:
        role_spec = {"strategy": "role", "role": value, "name": "n"}
        document = _doc(form=_form(submit_button=role_spec))
    path = _write(tmp_path, document)
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(path, APPROVAL_REF, tmp_path)
    assert info.value.reason is SelectorsReason.FORBIDDEN_SELECTOR_SYNTAX
    assert not any(ch.isdigit() for ch in str(info.value))


def test_enter_frame_is_rejected_in_challenge_markers(tmp_path: Path) -> None:
    marker = {"strategy": "css", "value": "div >> internal:control=enter-frame"}
    path = _write(tmp_path, _doc(detection=_detection(challenge_markers=[marker])))
    with pytest.raises(SelectorsNotValidatedError) as info:
        _load_validated(path, APPROVAL_REF, tmp_path)
    assert info.value.reason is SelectorsReason.FORBIDDEN_SELECTOR_SYNTAX


def test_unknown_aria_role_is_a_configuration_error(tmp_path: Path) -> None:
    spec = {"strategy": "role", "role": "boton-inexistente", "name": "n"}
    _fails(
        _write(tmp_path, _doc(form=_form(submit_button=spec))), SelectorsReason.INVALID_STRUCTURE
    )


def test_aria_roles_match_playwright_literal() -> None:
    import re

    import playwright.sync_api as sync_api

    from rut_checker.adapters.dian_portal.models import ARIA_ROLES

    source = Path(sync_api.__file__).with_name("_generated.py").read_text(encoding="utf-8")
    start = source.index("def get_by_role")
    block = source[start : source.index("]", start)]
    assert set(re.findall(r'"([a-z]+)"', block)) == set(ARIA_ROLES)
