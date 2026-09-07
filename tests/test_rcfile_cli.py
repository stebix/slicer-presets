import ast
from pathlib import Path

import pytest

from slicer_presets import cli, rcfile


def test_render_is_valid_python_and_embeds_home(tmp_path):
    text = rcfile.render(tmp_path)
    ast.parse(text)
    assert repr(str(tmp_path)) in text
    assert rcfile.is_generated(text)
    assert "slicer_presets.install()" in text.replace("_slicer_presets", "slicer_presets")


def test_install_rc_refuses_foreign_file_unless_forced(tmp_path):
    rc = tmp_path / ".slicerrc.py"
    rc.write_text("print('mine')\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rcfile.install_rc(tmp_path, rc)
    target, backup = rcfile.install_rc(tmp_path, rc, force=True)
    assert target == rc and backup is not None and backup.read_text() == "print('mine')\n"
    assert rcfile.is_generated(rc.read_text())
    # our own file is replaced without --force (and still backed up)
    target, backup2 = rcfile.install_rc(tmp_path / "other", rc)
    assert backup2 is not None and repr(str(tmp_path / "other")) in rc.read_text()


def test_rc_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SLICERRC", str(tmp_path / "rc.py"))
    assert rcfile.rc_path() == tmp_path / "rc.py"
    monkeypatch.delenv("SLICERRC")
    assert rcfile.rc_path() == Path.home() / ".slicerrc.py"


def test_cli_validate_and_install_rc_print(capsys, tmp_path):
    assert cli.main(["validate"]) == 0
    out = capsys.readouterr().out
    assert "InnerEar" in out and "Cochlea" in out and "label   1" in out

    assert cli.main(["--home", str(tmp_path), "install-rc", "--print"]) == 0
    assert repr(str(tmp_path)) in capsys.readouterr().out

    assert cli.main(["validate", str(tmp_path / "nope.json")]) == 2
    assert "not found" in capsys.readouterr().err


def test_cli_sanitize(tmp_path, capsys):
    from tests.test_scene_files import SCENE

    mrml = tmp_path / "scene.mrml"
    mrml.write_text(SCENE, encoding="utf-8")
    assert cli.main(["sanitize", str(mrml)]) == 0
    assert (tmp_path / "scene.safe.mrml").exists()
    assert cli.main(["sanitize", str(mrml), "--in-place"]) == 0
    assert (tmp_path / "scene.mrml.bak").exists()
    assert "activeEffectName" not in mrml.read_text(encoding="utf-8")
    assert cli.main(["sanitize", str(mrml)]) == 0
    assert "already clean" in capsys.readouterr().out


def test_slicer_install_ranking(monkeypatch, tmp_path):
    root = tmp_path / "slicer.org"
    for name in ("Slicer 5.8.1", "3D Slicer 5.10.0", "Slicer 5.11.0-2026-03-01", "Slicer"):
        (root / name).mkdir(parents=True)
        (root / name / "Slicer.exe").write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    ranked = [exe.parent.name for _, exe in cli.slicer_installs()]
    assert ranked == ["Slicer 5.11.0-2026-03-01", "3D Slicer 5.10.0", "Slicer 5.8.1"]
    monkeypatch.setenv("SLICER_EXE", str(root / "Slicer 5.8.1" / "Slicer.exe"))
    assert cli.find_slicer().parent.name == "Slicer 5.8.1"
