"""Pruebas de `infra/paths.py` (T-40b, ARQUITECTURA §6 y §11, Obs-4)."""

import importlib
import os
import stat
from pathlib import Path

import pytest

from rut_checker.domain.errors import UnsafePathError, UnsafePathReason
from rut_checker.infra import paths
from rut_checker.infra.paths import (
    assert_safe_dir,
    ensure_private_dir,
    is_synced_folder,
    resolve_output_path,
)
from rut_checker.infra.settings import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Elimina toda variable `RUT_*` heredada del entorno."""
    for name in list(os.environ):
        if name.upper().startswith("RUT_"):
            monkeypatch.delenv(name)


def lines(*items: str) -> str:
    """Une líneas de un `.gitignore` con salto final."""
    return chr(10).join(items) + chr(10)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Árbol git simulado (directorio `.git`) con raíz resuelta."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".gitignore").write_text(
        lines("# datos", "/output/", "logs/", "data"), encoding="utf-8"
    )
    return root.resolve()


@pytest.fixture
def foreign_repo(tmp_path: Path) -> Path:
    """Repo git ajeno: tiene `.git` pero su `.gitignore` no lista output/logs/data."""
    root = tmp_path / "foreign"
    (root / ".git").mkdir(parents=True)
    (root / ".gitignore").write_text(lines("*.pyc", "# output/"), encoding="utf-8")
    return root.resolve()


def make_settings(output_dir: Path) -> Settings:
    return Settings(_env_file=None, output_dir=output_dir)


def test_default_output_dir_is_allowed(repo: Path) -> None:
    for name in ("output", "logs", "data"):
        assert_safe_dir(repo / name)
        assert_safe_dir(repo / name / "sub" / "dir")


def test_custom_dir_inside_git_tree_is_rejected(repo: Path) -> None:
    for candidate in (repo / "src", repo / "outputs", repo, repo / "docs" / "output"):
        with pytest.raises(UnsafePathError) as info:
            assert_safe_dir(candidate)
        assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE
        assert str(candidate) not in str(info.value)


def test_git_file_marker_counts_as_repo(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    root.mkdir()
    (root / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        assert_safe_dir(root / "reports")


def test_dir_outside_git_tree_is_allowed(tmp_path: Path) -> None:
    assert_safe_dir(tmp_path / "anywhere")


def test_symlink_into_repo_is_rejected(tmp_path: Path, repo: Path) -> None:
    (repo / "src").mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(repo / "src", target_is_directory=True)
    except OSError:
        pytest.skip("no se pueden crear enlaces simbólicos en este entorno")
    with pytest.raises(UnsafePathError) as info:
        assert_safe_dir(link)
    assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE


def test_default_folder_symlinked_elsewhere_in_repo_is_rejected(repo: Path) -> None:
    (repo / "src").mkdir()
    try:
        (repo / "output").symlink_to(repo / "src", target_is_directory=True)
    except OSError:
        pytest.skip("no se pueden crear enlaces simbólicos en este entorno")
    with pytest.raises(UnsafePathError):
        assert_safe_dir(repo / "output")


def test_resolve_output_path_defaults_to_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert resolve_output_path(None, make_settings(out)) == out.resolve()


def test_salida_inside_output_dir_is_accepted(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = resolve_output_path(out / "lote1", make_settings(out))
    assert result == (out / "lote1").resolve()


def test_salida_relative_is_resolved_against_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.chdir(tmp_path)
    assert resolve_output_path(Path("lote1"), make_settings(out)) == (out / "lote1").resolve()


@pytest.mark.parametrize("requested", ["../escape", "sub/../../other", "..", "../out2"])
def test_salida_outside_output_dir_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requested: str
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(UnsafePathError) as info:
        resolve_output_path(Path(requested), make_settings(out))
    assert info.value.reason is UnsafePathReason.OUTSIDE_OUTPUT_DIR


def test_salida_prefix_sibling_is_rejected(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(UnsafePathError):
        resolve_output_path(tmp_path / "out2", make_settings(out))


def test_salida_symlink_escaping_output_dir_is_rejected(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (out / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("no se pueden crear enlaces simbólicos en este entorno")
    with pytest.raises(UnsafePathError):
        resolve_output_path(out / "link", make_settings(out))


def test_salida_with_nul_character_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError) as info:
        resolve_output_path(Path("a\x00b"), make_settings(tmp_path / "out"))
    assert info.value.reason is UnsafePathReason.INVALID_PATH


def test_output_dir_inside_git_tree_is_rejected_by_resolve(repo: Path) -> None:
    with pytest.raises(UnsafePathError) as info:
        resolve_output_path(None, make_settings(repo / "docs"))
    assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("home", "OneDrive", "x"), True),
        (("home", "OneDrive - Empresa SAS", "x"), True),
        (("home", "Dropbox", "x"), True),
        (("home", "Google Drive", "x"), True),
        (("home", "My Drive", "x"), True),
        (("home", "proyectos", "x"), False),
    ],
)
def test_is_synced_folder(tmp_path: Path, parts: tuple[str, ...], expected: bool) -> None:
    assert is_synced_folder(tmp_path.joinpath(*parts)) is expected


def test_ensure_private_dir_creates_nested_directory(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"
    ensure_private_dir(target)
    assert target.is_dir()
    ensure_private_dir(target)  # idempotente


@pytest.mark.skipif(os.name != "posix", reason="los modos POSIX no aplican en Windows")
def test_ensure_private_dir_uses_mode_0700(tmp_path: Path) -> None:
    target = tmp_path / "private"
    ensure_private_dir(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_ensure_private_dir_refuses_unsafe_dir(repo: Path) -> None:
    with pytest.raises(UnsafePathError):
        ensure_private_dir(repo / "docs")
    assert not (repo / "docs").exists()


def test_default_name_in_foreign_repo_without_ignore_is_rejected(foreign_repo: Path) -> None:
    for name in ("output", "logs", "data"):
        with pytest.raises(UnsafePathError) as info:
            assert_safe_dir(foreign_repo / name)
        assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE


def test_default_name_with_project_gitignore_is_allowed(repo: Path) -> None:
    assert_safe_dir(repo / "output" / "x")
    assert_safe_dir(repo / "logs")
    assert_safe_dir(repo / "data")


def test_negated_ignore_line_is_rejected(foreign_repo: Path) -> None:
    (foreign_repo / ".gitignore").write_text(lines("output/", "!output/keep"), encoding="utf-8")
    with pytest.raises(UnsafePathError):
        assert_safe_dir(foreign_repo / "output")


def test_real_project_gitignore_covers_default_dirs() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in ("output", "logs", "data"):
        assert_safe_dir(root / name)


def test_ignored_default_dirs_match_settings_defaults() -> None:
    defaults = tuple(
        Settings.model_fields[field].default.name for field in ("output_dir", "log_dir", "data_dir")
    )
    assert set(defaults) == set(paths.IGNORED_DEFAULT_DIRS)


def test_ensure_private_dir_detects_link_planted_during_mkdir(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "src").mkdir()
    target = tmp_path / "target"

    def planting_mkdir(
        self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        try:
            self.symlink_to(repo / "src", target_is_directory=True)
        except OSError:
            pytest.skip("no se pueden crear enlaces simbólicos en este entorno")

    monkeypatch.setattr(Path, "mkdir", planting_mkdir)
    with pytest.raises(UnsafePathError):
        ensure_private_dir(target)


def test_ensure_private_dir_mkdir_failure_has_no_path_or_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "secreto1234567"

    def failing_mkdir(
        self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)
    with pytest.raises(UnsafePathError) as info:
        ensure_private_dir(secret)
    assert info.value.reason is UnsafePathReason.INVALID_PATH
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    assert "secreto" not in str(info.value)


def test_resolve_output_path_rejects_nested_git_repo(tmp_path: Path) -> None:
    out = tmp_path / "out"
    (out / "nested" / ".git").mkdir(parents=True)
    with pytest.raises(UnsafePathError) as info:
        resolve_output_path(out / "nested" / "x", make_settings(out))
    assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE


@pytest.mark.parametrize(
    "bad",
    [
        "file.txt:stream",
        "CON",
        "con",
        "Nul.txt",
        "COM1",
        "lpt9.log",
        "AUX",
        "PRN",
        "name.",
        "name ",
    ],
)
def test_windows_unsafe_components_are_rejected(tmp_path: Path, bad: str) -> None:
    out = tmp_path / "out"
    with pytest.raises(UnsafePathError) as info:
        resolve_output_path(Path(bad), make_settings(out))
    assert info.value.reason is UnsafePathReason.INVALID_PATH
    with pytest.raises(UnsafePathError):
        assert_safe_dir(tmp_path / bad)


def test_reserved_lookalike_names_are_allowed(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert resolve_output_path(Path("console"), make_settings(out)).name == "console"
    assert resolve_output_path(Path("COM10"), make_settings(out)).name == "COM10"


def test_resolve_failure_has_no_chained_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Path, strict: bool = False) -> Path:
        raise OSError("detalle con ruta")

    monkeypatch.setattr(Path, "resolve", boom)
    with pytest.raises(UnsafePathError) as info:
        assert_safe_dir(Path("x"))
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_is_synced_folder_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Path, strict: bool = False) -> Path:
        raise OSError("x")

    monkeypatch.setattr(Path, "resolve", boom)
    assert is_synced_folder(Path("x")) is False


@pytest.mark.parametrize("name", ["iCloudDrive", "Box", "Nextcloud", "Box Sync"])
def test_is_synced_folder_other_providers(tmp_path: Path, name: str) -> None:
    assert is_synced_folder(tmp_path / name / "x") is True


def test_is_synced_folder_uses_onedrive_env_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "corporativo"
    monkeypatch.setenv("OneDriveCommercial", str(root))
    assert is_synced_folder(root / "docs") is True
    assert is_synced_folder(tmp_path / "otra") is False


@pytest.mark.skipif(os.name != "nt", reason="las junctions solo existen en Windows")
def test_junction_into_repo_is_rejected(tmp_path: Path, repo: Path) -> None:
    (repo / "src").mkdir()
    link = tmp_path / "junction"
    # `_winapi.CreateJunction` es API privada, pero es la única forma de crear una junction sin
    # privilegios de administrador (os.symlink los exige) desde la biblioteca estándar.
    winapi = importlib.import_module("_winapi")
    winapi.CreateJunction(str(repo / "src"), str(link))
    with pytest.raises(UnsafePathError) as info:
        assert_safe_dir(link)
    assert info.value.reason is UnsafePathReason.INSIDE_GIT_TREE
