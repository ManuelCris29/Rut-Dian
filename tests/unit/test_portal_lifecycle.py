"""Pruebas de arquitectura (ast) del ciclo de vida del navegador en `adapters/dian_portal` (T-49).

Complementan `test_portal_architecture.py` (APIs prohibidas): quién crea el contexto y las
páginas, quién lanza el navegador (siempre visible), qué módulos actúan sobre la página, quién
puede construir la fuente y los límites de tamaño. Solo miran `src`.
"""

import ast

import pytest
from test_portal_architecture import ACTIONS_FORBIDDEN_IN_PASSIVE_MODULES, PORTAL_DIR, SRC

SESSION_OWNER = "source.py"
FACTORY = "factory.py"
# Función donde se permite crear contexto/página: el arranque del lote; la página nueva también
# al reemplazarla ante `SessionExpired` (único caso, ADR-0003 §3).
ALLOWED_CREATION_SITES = {
    "new_context": {"_start"},
    "new_page": {"_start", "_replace_page"},
}
ACTIVE_MODULES = ("form_flow.py",)
ALLOWED_ACTIVE_ACTIONS = {"fill", "click", "goto"}
SEAM_KEYWORDS = {"launcher", "base_url", "session_probe"}
MAX_MODULE_LINES = 300
MAX_FUNCTION_LINES = 40


def call_sites(source: str, names: set[str]) -> list[tuple[str, str]]:
    """(atributo, función que lo contiene) de cada acceso a un atributo de `names`.

    Detecta el acceso aunque no se llame (`run_translated(page.click)`).
    """
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, function: str) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            function = node.name
        if isinstance(node, ast.Attribute) and node.attr in names:
            found.append((node.attr, function))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(ast.parse(source), "")
    return found


def _portal_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in PORTAL_DIR.rglob("*.py")}


def test_call_sites_reports_the_innermost_declared_function() -> None:
    source = "def _start():\n    b.new_context()\n\ndef other():\n    b.new_page()\nb.launch()\n"
    assert call_sites(source, {"new_context"}) == [("new_context", "_start")]
    assert call_sites(source, {"new_page"}) == [("new_page", "other")]
    assert call_sites(source, {"launch"}) == [("launch", "")]


@pytest.mark.parametrize(
    "source", ["run_translated(page.click)", "run_translated(page.evaluate)", "f = page.fill"]
)
def test_call_sites_detects_uncalled_attribute_references(source: str) -> None:
    assert call_sites(source, ACTIONS_FORBIDDEN_IN_PASSIVE_MODULES)


def test_context_and_pages_are_created_only_at_batch_start_in_source() -> None:
    offenders: list[str] = []
    for name, text in _portal_sources().items():
        for attr, function in call_sites(text, set(ALLOWED_CREATION_SITES)):
            if name != SESSION_OWNER or function not in ALLOWED_CREATION_SITES[attr]:
                offenders.append(f"{name}:{attr}@{function}")
    assert not offenders, offenders


def _calls(text: str, attr: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr
    ]


def _is_false(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def test_only_source_starts_playwright_and_always_launches_visible() -> None:
    launches: list[ast.Call] = []
    for name, text in _portal_sources().items():
        starts = call_sites(text, {"launch", "start"})
        names = {n.id for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Name)}
        assert not (starts or "sync_playwright" in names) or name == SESSION_OWNER, name
        launches += _calls(text, "launch")
    assert len(launches) == 1
    keywords = {kw.arg: kw.value for kw in launches[0].keywords}
    assert set(keywords) == {"headless"}  # sin args, proxy, user_agent...
    assert _is_false(keywords["headless"])


def test_the_single_context_disables_downloads_and_takes_no_other_options() -> None:
    contexts = _calls(_portal_sources()[SESSION_OWNER], "new_context")
    assert len(contexts) == 1
    keywords = {kw.arg: kw.value for kw in contexts[0].keywords}
    assert set(keywords) == {"accept_downloads"}
    assert _is_false(keywords["accept_downloads"])


def test_page_actions_are_limited_to_the_form_flow() -> None:
    for name, text in _portal_sources().items():
        used = {attr for attr, _ in call_sites(text, ACTIONS_FORBIDDEN_IN_PASSIVE_MODULES)}
        if name in ACTIVE_MODULES:
            assert used <= ALLOWED_ACTIVE_ACTIONS, (name, used - ALLOWED_ACTIVE_ACTIONS)
        else:
            assert not used, (name, used)


def test_source_is_built_only_by_the_factory_without_test_seams() -> None:
    builders: list[str] = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "DianPortalSource":
                builders.append(path.name)
                assert not {kw.arg for kw in node.keywords} & SEAM_KEYWORDS, path.name
    assert builders == [FACTORY]


def test_playwright_objects_do_not_cross_the_module_boundary() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name == SESSION_OWNER:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            params = [a.annotation for a in node.args.args + node.args.kwonlyargs]
            names = {getattr(a, "id", None) for a in [*params, node.returns]}
            if names & {"Playwright", "Browser"}:
                offenders.append(f"{path.name}:{node.name}")
    assert not offenders, offenders


def test_portal_modules_and_functions_stay_small() -> None:
    for name, text in _portal_sources().items():
        assert len(text.splitlines()) <= MAX_MODULE_LINES, name
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                body = node.body
                has_doc = isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                first = body[1] if has_doc and len(body) > 1 else body[0]
                size = (node.end_lineno or 0) - first.lineno + 1  # sin cuenta de la docstring
                assert size <= MAX_FUNCTION_LINES, (name, node.name)
