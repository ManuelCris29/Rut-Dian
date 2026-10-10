"""Pruebas del detector `portal_violations` (muestras de código prohibido y permitido)."""

import pytest
from test_portal_architecture import portal_violations


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("p.launch(proxy={'server': 'x'})", {"proxy"}),
        (
            "b.new_context(user_agent='x', ignore_https_errors=True)",
            {"user_agent", "ignore_https_errors"},
        ),
        ("p.launch(args=['--x'])", {"args"}),
        ("p.launch(ignore_default_args=['--y'])", {"ignore_default_args"}),
        ("c.add_init_script('x')", {"add_init_script"}),
        ("c.route('**/*', h)", {"route"}),
        ("page.frame_locator('iframe')", {"frame_locator"}),
        ("el.content_frame()", {"content_frame"}),
        ("page.pause()", {"pause"}),
        ("c.tracing.start()", {"tracing"}),
        ("page.screenshot(path='x.png')", {"screenshot"}),
        ("c.clear_cookies()", {"clear_cookies"}),
        (
            "b.new_context(record_video_dir='v', record_har_path='h')",
            {"record_video_dir", "record_har_path"},
        ),
        ("b.new_context(extra_http_headers={})", {"extra_http_headers"}),
        ("b.new_context(**{'proxy': 1})", {"proxy"}),
        ("page.mouse.click(1, 2)", {"mouse"}),
        ("page.keyboard.press('a')", {"keyboard"}),
        ("page.touchscreen.tap(1, 2)", {"touchscreen"}),
        ("page.frames", {"frames"}),
        ("page.main_frame.child_frames", {"child_frames"}),
        ("page.expose_function('f', g)", {"expose_function"}),
        ("c.add_cookies([])", {"add_cookies"}),
        ("c.storage_state()", {"storage_state"}),
        ("c.route_web_socket('x', h)", {"route_web_socket"}),
        ("c.new_cdp_session(p)", {"new_cdp_session"}),
        ("p.chromium.connect_over_cdp('x')", {"connect_over_cdp"}),
        ("p.chromium.launch_persistent_context('d')", {"launch_persistent_context"}),
        ("page.wait_for_function('1')", {"wait_for_function"}),
        ("b.new_context(bypass_csp=True, locale='es')", {"bypass_csp", "locale"}),
        ("b.new_context(permissions=['geolocation'])", {"permissions"}),
        ("p.launch(executable_path='x', devtools=True)", {"executable_path", "devtools"}),
        ("p.launch(headless=True)", {"headless"}),
        ("p.launch(headless=flag)", {"headless"}),
        ("getattr(page, 'route')", {"getattr", "route"}),
        ("setattr(page, 'mouse', 1)", {"setattr", "mouse"}),
        ("operator.methodcaller('pause')", {"methodcaller", "pause"}),
        ("operator.attrgetter('keyboard')(page)", {"attrgetter", "keyboard"}),
        ("page.__getattribute__('x')", {"__getattribute__"}),
        ("eval('1')", {"eval"}),
        ("exec('x = 1')", {"exec"}),
        ("compile('1', 'f', 'eval')", {"compile"}),
        ("__import__('os')", {"__import__"}),
        ("vars(page)", {"vars"}),
        ("page.__dict__", {"__dict__"}),
        ("inspect.getattr_static(page, 'x')", {"getattr_static"}),
        ("from inspect import getattr_static", {"getattr_static"}),
    ],
)
def test_portal_detector_flags_forbidden_apis(source: str, expected: set[str]) -> None:
    assert expected <= portal_violations(source)


def test_portal_detector_allows_re_compile_attribute() -> None:
    assert portal_violations("import re; re.compile('x')") == set()


def test_exemptions_are_limited_to_the_node_type() -> None:
    frame_constant = "X = ('frame',)"
    assert portal_violations(frame_constant, allow_frame_constant=True) == set()
    assert portal_violations(frame_constant) == {"frame"}
    # La exención de `frame` no cubre el atributo `.frame` ni otras violaciones.
    assert portal_violations("page.frame", allow_frame_constant=True) == {"frame"}
    assert portal_violations("page.route('x')", allow_frame_constant=True) == {"route"}
    getattr_call = "getattr(event, 'anchor', None)"
    assert portal_violations(getattr_call, allow_getattr_call=True) == set()
    assert portal_violations(getattr_call) == {"getattr"}
    # No cubre `getattr` sin llamar (alias), ni nombres prohibidos como argumento.
    assert portal_violations("f = getattr", allow_getattr_call=True) == {"getattr"}
    assert portal_violations("getattr(page, 'route')", allow_getattr_call=True) == {"route"}


def test_portal_detector_allows_passive_calls_and_headless_false() -> None:
    source = (
        "page.get_by_test_id('x').is_visible()\n"
        "response.status\n"
        "locator.wait_for(state='visible')\n"
        "p.launch(headless=False)"
    )
    assert portal_violations(source) == set()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("c.request.post('x')", {"request"}),
        ("p.chromium.launch(headless=False, args=[])", {"args"}),
        ("b.new_context(proxy=None)", {"proxy"}),
        ("c.clear_cookies()", {"clear_cookies"}),
        ("b.new_context(accept_downloads=True)", {"accept_downloads"}),
        ("b.new_context(accept_downloads=flag)", {"accept_downloads"}),
        ("b.new_context(**{'accept_downloads': 1})", {"accept_downloads"}),
    ],
)
def test_portal_detector_flags_more_forbidden_apis(source: str, expected: set[str]) -> None:
    assert expected <= portal_violations(source)


def test_portal_detector_allows_downloads_disabled() -> None:
    assert portal_violations("b.new_context(accept_downloads=False)") == set()
