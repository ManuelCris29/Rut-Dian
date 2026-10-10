"""Pruebas de arquitectura por capas (ARQUITECTURA §4) con ``ast``."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "rut_checker"
ROOT = "rut_checker"
CORE_LAYERS = ("domain", "ports", "application")
FORBIDDEN_EXTERNAL = {"playwright", "typer", "openpyxl", "yaml"}
FORBIDDEN_INTERNAL = {f"{ROOT}.{name}" for name in ("adapters", "io", "infra", "cli")}
# Dirección de dependencias: domain <- ports <- application (nunca al revés).
FORBIDDEN_BY_DIRECTION = {
    "domain": {f"{ROOT}.ports", f"{ROOT}.application"},
    "ports": {f"{ROOT}.application"},
    "application": set(),
}
# Lista blanca estricta de domain: stdlib + pydantic + stdnum + el propio domain.
DOMAIN_ALLOWED_ROOTS = set(sys.stdlib_module_names) | {"pydantic", "stdnum"}
DYNAMIC_IMPORTERS = {"import_module", "__import__"}


def _matches(module: str, prefixes: set[str]) -> bool:
    return any(module == p or module.startswith(f"{p}.") for p in prefixes)


def _resolve_relative(module_name: str, is_package: bool, level: int, target: str | None) -> str:
    """Convierte un import relativo en nombre absoluto según el paquete del archivo."""
    parts = module_name.split(".")
    package = parts if is_package else parts[:-1]
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, target] if target else base)


def _dynamic_literal(node: ast.Call) -> str | None:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name in DYNAMIC_IMPORTERS and node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def imported_modules(source: str, module_name: str, is_package: bool = False) -> set[str]:
    """Módulos importados (absolutos), incluyendo ``modulo.alias`` y ``import_module("x")``."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = _resolve_relative(module_name, is_package, node.level, node.module)
            else:
                module = node.module or ""
            modules.add(module)
            modules.update(f"{module}.{a.name}" for a in node.names if a.name != "*")
        elif isinstance(node, ast.Call) and (literal := _dynamic_literal(node)):
            modules.add(literal)
    return modules


def layer_violations(layer: str, modules: set[str]) -> set[str]:
    """Imports que una capa núcleo no puede hacer."""
    forbidden = FORBIDDEN_EXTERNAL | FORBIDDEN_INTERNAL | FORBIDDEN_BY_DIRECTION[layer]
    bad = {m for m in modules if _matches(m, forbidden)}
    if layer == "domain":
        own = {f"{ROOT}.domain"}
        bad |= {
            m
            for m in modules
            if m != ROOT and m.split(".")[0] not in DOMAIN_ALLOWED_ROOTS and not _matches(m, own)
        }
    return bad


def _file_imports(path: Path) -> set[str]:
    relative = path.relative_to(SRC.parent).with_suffix("")
    is_package = relative.name == "__init__"
    parts = relative.parts[:-1] if is_package else relative.parts
    return imported_modules(path.read_text(encoding="utf-8"), ".".join(parts), is_package)


def test_core_layers_do_not_import_forbidden_modules() -> None:
    found: dict[str, set[str]] = {}
    for layer in CORE_LAYERS:
        files = sorted((SRC / layer).rglob("*.py"))
        assert files, f"la capa {layer} debe existir"
        for path in files:
            if bad := layer_violations(layer, _file_imports(path)):
                found[str(path.relative_to(SRC))] = bad
    assert not found, f"imports prohibidos en capas núcleo: {found}"


def test_only_dian_portal_package_imports_playwright() -> None:
    allowed = SRC / "adapters" / "dian_portal"
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if allowed not in path.parents and _matches_any(_file_imports(path), {"playwright"})
    ]
    assert not offenders, f"solo adapters/dian_portal puede importar playwright: {offenders}"


def _matches_any(modules: set[str], prefixes: set[str]) -> bool:
    return any(_matches(m, prefixes) for m in modules)


@pytest.mark.parametrize(
    ("layer", "module_name", "source", "expected"),
    [
        ("domain", "rut_checker.domain.x", "from ..infra import settings", {"rut_checker.infra"}),
        (
            "domain",
            "rut_checker.domain.x",
            "from rut_checker import adapters",
            {"rut_checker.adapters"},
        ),
        ("domain", "rut_checker.domain.x", "import openpyxl", {"openpyxl"}),
        (
            "application",
            "rut_checker.application.x",
            "import importlib\nimportlib.import_module('rut_checker.io.readers')",
            {"rut_checker.io.readers"},
        ),
        ("ports", "rut_checker.ports.x", "__import__('playwright')", {"playwright"}),
        (
            "application",
            "rut_checker.application.x",
            "from rut_checker import cli",
            {"rut_checker.cli"},
        ),
        ("domain", "rut_checker.domain.x", "import requests", {"requests"}),
        ("domain", "rut_checker.domain.x", "from ..ports import rut_source", {"rut_checker.ports"}),
        (
            "ports",
            "rut_checker.ports.x",
            "from ..application import batch_service",
            {"rut_checker.application"},
        ),
    ],
)
def test_detector_flags_forbidden_imports(
    layer: str, module_name: str, source: str, expected: set[str]
) -> None:
    found = layer_violations(layer, imported_modules(source, module_name))
    assert expected <= found


@pytest.mark.parametrize(
    ("layer", "module_name", "source"),
    [
        ("domain", "rut_checker.domain.x", "from rut_checker.domain import status"),
        ("domain", "rut_checker.domain.x", "import pydantic\nfrom stdnum.co import nit"),
        ("domain", "rut_checker.domain.x", "from . import status\nimport re, enum"),
        ("application", "rut_checker.application.x", "from rut_checker.ports import rut_source"),
        ("application", "rut_checker.application.x", "from ..domain import models"),
        ("ports", "rut_checker.ports.x", "from rut_checker.domain.models import Result"),
    ],
)
def test_detector_allows_valid_imports(layer: str, module_name: str, source: str) -> None:
    assert layer_violations(layer, imported_modules(source, module_name)) == set()


@pytest.mark.parametrize(
    "package", [*CORE_LAYERS, "adapters", "adapters/dian_portal", "io", "infra"]
)
def test_package_skeleton_exists(package: str) -> None:
    assert (SRC / package / "__init__.py").is_file()


def _calls_get_logger(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "getLogger":
                return True
    return False


def test_only_infra_logging_calls_get_logger() -> None:
    allowed = SRC / "infra" / "logging.py"
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path != allowed and _calls_get_logger(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"solo infra/logging.py puede llamar getLogger: {offenders}"


def test_get_logger_detector() -> None:
    assert _calls_get_logger("import logging\nlogging.getLogger('x')")
    assert _calls_get_logger("from logging import getLogger\ngetLogger()")
    assert not _calls_get_logger("def f(logger):\n    logger.info('x')")
