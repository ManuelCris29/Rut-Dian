import rut_checker


def test_version_is_declared() -> None:
    assert isinstance(rut_checker.__version__, str)
    assert rut_checker.__version__
