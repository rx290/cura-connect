import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "installer"))
from install import cura_base_dir, find_version_dirs, install_plugin


def test_cura_base_dir_windows_uses_appdata():
    base = cura_base_dir("Windows", Path("/home/x"), {"APPDATA": "C:/Users/x/AppData/Roaming"})
    assert base == Path("C:/Users/x/AppData/Roaming/cura")


def test_cura_base_dir_windows_falls_back_without_appdata():
    base = cura_base_dir("Windows", Path("/home/x"), {})
    assert base == Path("/home/x/AppData/Roaming/cura")


def test_cura_base_dir_macos():
    base = cura_base_dir("Darwin", Path("/Users/x"), {})
    assert base == Path("/Users/x/Library/Application Support/cura")


def test_cura_base_dir_linux_respects_xdg_data_home():
    base = cura_base_dir("Linux", Path("/home/x"), {"XDG_DATA_HOME": "/home/x/.data"})
    assert base == Path("/home/x/.data/cura")


def test_cura_base_dir_linux_default():
    base = cura_base_dir("Linux", Path("/home/x"), {})
    assert base == Path("/home/x/.local/share/cura")


def test_find_version_dirs_ignores_backups_and_zips(tmp_path):
    (tmp_path / "5.13").mkdir()
    (tmp_path / "5.10").mkdir()
    (tmp_path / "5.13.backup_before_profile_copy").mkdir()
    (tmp_path / "5.13_20260707_131333.zip").write_text("not a dir")
    (tmp_path / "stdout.log").write_text("noise")

    versions = find_version_dirs(tmp_path)

    assert [v.name for v in versions] == ["5.10", "5.13"]


def test_find_version_dirs_missing_base_dir_returns_empty(tmp_path):
    assert find_version_dirs(tmp_path / "does_not_exist") == []


def test_install_plugin_copies_source_into_plugins_subfolder(tmp_path):
    source = tmp_path / "source" / "CuraConnect"
    source.mkdir(parents=True)
    (source / "plugin.json").write_text("{}")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "stale.pyc").write_text("x")
    version_dir = tmp_path / "5.13"
    version_dir.mkdir()

    dest = install_plugin(source, version_dir)

    assert dest == version_dir / "plugins" / "CuraConnect" / "CuraConnect"
    assert (dest / "plugin.json").exists()
    assert not (dest / "__pycache__").exists()


def test_install_plugin_replaces_a_stale_existing_copy(tmp_path):
    source = tmp_path / "source" / "CuraConnect"
    source.mkdir(parents=True)
    (source / "plugin.json").write_text('{"version": "0.2.0"}')
    version_dir = tmp_path / "5.13"
    stale = version_dir / "plugins" / "CuraConnect" / "CuraConnect"
    stale.mkdir(parents=True)
    (stale / "plugin.json").write_text('{"version": "0.1.0"}')
    (stale / "leftover_removed_file.py").write_text("x")

    dest = install_plugin(source, version_dir)

    assert (dest / "plugin.json").read_text() == '{"version": "0.2.0"}'
    assert not (dest / "leftover_removed_file.py").exists()
