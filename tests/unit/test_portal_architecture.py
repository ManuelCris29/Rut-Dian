"""Pruebas de arquitectura del adaptador del portal (ADR-0003 §3, ARQUITECTURA §4) con ``ast``.

Solo miran ``src/rut_checker/adapters/dian_portal``: los tests sí pueden usar ``route``/``args``.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "rut_checker"

# --- Prohibiciones del adaptador del portal (ADR-0003 §3, ARQUITECTURA §4, Obs-2/5/12) ---------
PORTAL_DIR = SRC / "adapters" / "dian_portal"
# Argumentos con nombre (launch/new_context/etc.) que ocultan la automatización, alteran el
# navegador o dejan rastro. Los tests sí pueden usar `args`/`route`: la prueba solo mira `src`.
FORBIDDEN_KEYWORDS = {
    "user_agent",
    "proxy",
    "args",
    "ignore_default_args",
    "extra_http_headers",
    "ignore_https_errors",
    "record_video_dir",
    "record_har_path",
    "bypass_csp",
    "java_script_enabled",
    "locale",
    "timezone_id",
    "geolocation",
    "permissions",
    "device_scale_factor",
    "is_mobile",
    "has_touch",
    "storage_state",
    "user_data_dir",
    "executable_path",
    "chromium_sandbox",
    "devtools",
}
# Métodos/atributos prohibidos en el código de producción del adaptador.
CORE_FORBIDDEN_ATTRIBUTES = {
    "route",
    "add_init_script",
    "clear_cookies",
    "frame_locator",
    "content_frame",
    "pause",
    "tracing",
    "screenshot",
    "request",  # APIRequestContext: HTTP directo que evita el navegador visible
}
FORBIDDEN_ATTRIBUTES = CORE_FORBIDDEN_ATTRIBUTES | {
    "mouse",
    "keyboard",
    "touchscreen",
    "frame",
    "frames",
    "child_frames",
    "expose_function",
    "expose_binding",
    "set_extra_http_headers",
    "add_cookies",
    "storage_state",
    "grant_permissions",
    "set_geolocation",
    "emulate_media",
    "route_from_har",
    "route_web_socket",
    "add_locator_handler",
    "new_cdp_session",
    "connect_over_cdp",
    "launch_persistent_context",
    "wait_for_function",
    "__getattribute__",
}
# Acceso dinámico a atributos: se vigilan por nombre y, además, cualquier cadena igual a un
# nombre prohibido (p. ej. `getattr(page, "route")`).
DYNAMIC_ACCESSORS = {"getattr", "setattr", "methodcaller", "attrgetter", "__getattribute__"}
# La detección y los localizadores son pasivos: ninguna acción sobre la página.
ACTIONS_FORBIDDEN_IN_PASSIVE_MODULES = {
    "click",
    "dblclick",
    "fill",
    "type",
    "press",
    "hover",
    "focus",
    "check",
    "uncheck",
    "set_checked",
    "tap",
    "evaluate",
    "evaluate_handle",
    "dispatch_event",
    "scroll_into_view_if_needed",
    "set_input_files",
    "select_option",
    "reload",
    "drag_to",
    "blur",
    "clear",
    "press_sequentially",
    "select_text",
    "highlight",
    "goto",
    "go_back",
    "go_forward",
}
PASSIVE_MODULES = ("detection.py", "locators.py", "waiting.py", "assisted_wait.py")
# Ejecución/introspección dinámica prohibida: como nombre (builtins) o, para los dos últimos,
# también como atributo (`re.compile` es legítimo, por eso `compile` solo se vigila como nombre).
FORBIDDEN_BUILTIN_NAMES = {"eval", "exec", "compile", "__import__", "vars"}
FORBIDDEN_INTROSPECTION = {"__dict__", "getattr_static"}
# Exenciones puntuales, acotadas al tipo de nodo (no a todo el archivo):
# - models.py: solo la constante de texto "frame" (subcadena que se RECHAZA en los selectores, M-1).
# - yaml_loader.py: solo la llamada directa a `getattr` sobre un evento de pyyaml.
EXEMPT_FRAME_CONSTANT = {"models.py"}
EXEMPT_GETATTR_CALL = {"yaml_loader.py"}


# Argumentos que solo admiten el literal False: navegador visible y sin descargas (B-1/B-4).
ONLY_FALSE_KEYWORDS = {"headless", "accept_downloads"}


def _keyword_violations(node: ast.keyword) -> set[str]:
    found: set[str] = set()
    if node.arg in FORBIDDEN_KEYWORDS:
        found.add(str(node.arg))
    only_false = node.arg in ONLY_FALSE_KEYWORDS
    if only_false and not (isinstance(node.value, ast.Constant) and node.value.value is False):
        found.add(str(node.arg))
    return found


def _name_violations(node: ast.Name, call_funcs: set[int], allow_getattr_call: bool) -> set[str]:
    found: set[str] = set()
    if node.id in CORE_FORBIDDEN_ATTRIBUTES - {"pause"}:
        found.add(node.id)  # p. ej. `from x import frame_locator`
    if node.id in FORBIDDEN_BUILTIN_NAMES | FORBIDDEN_INTROSPECTION:
        found.add(node.id)
    if node.id in DYNAMIC_ACCESSORS and not (
        allow_getattr_call and node.id == "getattr" and id(node) in call_funcs
    ):
        found.add(node.id)
    return found


def portal_violations(
    source: str, *, allow_frame_constant: bool = False, allow_getattr_call: bool = False
) -> set[str]:
    """Usos prohibidos en el código del adaptador: kwargs, atributos, cadenas y `headless`."""
    found: set[str] = set()
    every_name = (
        FORBIDDEN_KEYWORDS
        | ONLY_FALSE_KEYWORDS
        | FORBIDDEN_ATTRIBUTES
        | DYNAMIC_ACCESSORS
        | FORBIDDEN_BUILTIN_NAMES
        | FORBIDDEN_INTROSPECTION
    )
    tree = ast.parse(source)
    call_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            found |= _keyword_violations(node)
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES | FORBIDDEN_INTROSPECTION:
                found.add(node.attr)
            if node.attr in DYNAMIC_ACCESSORS:
                found.add(node.attr)
        if isinstance(node, ast.Name):
            found |= _name_violations(node, call_funcs, allow_getattr_call)
        if isinstance(node, ast.ImportFrom | ast.Import):
            found |= {a.name for a in node.names if a.name in FORBIDDEN_INTROSPECTION}
        exempt = allow_frame_constant and isinstance(node, ast.Constant) and node.value == "frame"
        if isinstance(node, ast.Constant) and node.value in every_name and not exempt:
            found.add(str(node.value))  # claves de dict, getattr(x, "route"), etc.
    return found


def test_dian_portal_package_uses_no_evasion_or_tracing_apis() -> None:
    found = {
        str(path.relative_to(PORTAL_DIR)): bad
        for path in PORTAL_DIR.rglob("*.py")
        if (
            bad := portal_violations(
                path.read_text(encoding="utf-8"),
                allow_frame_constant=path.name in EXEMPT_FRAME_CONSTANT,
                allow_getattr_call=path.name in EXEMPT_GETATTR_CALL,
            )
        )
    }
    assert not found, f"APIs prohibidas en adapters/dian_portal: {found}"


@pytest.mark.parametrize("module", PASSIVE_MODULES)
def test_detection_and_locators_are_passive(module: str) -> None:
    tree = ast.parse((PORTAL_DIR / module).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = called & ACTIONS_FORBIDDEN_IN_PASSIVE_MODULES
    assert not forbidden, forbidden


@pytest.mark.parametrize("module", ["models.py", "yaml_loader.py"])
def test_exempt_modules_do_not_import_playwright(module: str) -> None:
    tree = ast.parse((PORTAL_DIR / module).read_text(encoding="utf-8"))
    roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "playwright" not in roots
