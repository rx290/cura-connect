#!/usr/bin/env python3
"""Cross-platform installer for the CuraConnect plugin. Copies the plugin
into whichever Cura installation it finds, on Windows, macOS, or Linux,
with no manual folder-hunting required."""
import os
import platform
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "CuraConnect"


def cura_base_dir(system, home, env):
    """Where Cura keeps its per-user data (config, plugins, etc.) on each OS."""
    if system == "Windows":
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "cura"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "cura"
    return Path(env.get("XDG_DATA_HOME", str(home / ".local" / "share"))) / "cura"


def find_version_dirs(base_dir):
    """Cura's own version folders look like '5.13', not the backup/zip
    clutter Cura also drops next to them (e.g. '5.13.backup...', '5.13.zip')."""
    if not base_dir.is_dir():
        return []
    versions = []
    for entry in base_dir.iterdir():
        if entry.is_dir() and _is_version_name(entry.name):
            versions.append(entry)
    return sorted(versions, key=lambda p: _version_key(p.name))


def _is_version_name(name):
    parts = name.split(".")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def _version_key(name):
    return tuple(int(part) for part in name.split("."))


def install_plugin(source_dir, version_dir):
    """Drops `source_dir` (the plugin.json-containing folder) into
    `version_dir`/plugins/<PLUGIN_NAME>/<PLUGIN_NAME>, replacing any previous
    copy. Cura expects that double-nesting, a single level doesn't load.
    Removes the whole plugin_root first so a leftover file from an older
    or previously-broken install can't survive the update."""
    plugin_root = version_dir / "plugins" / PLUGIN_NAME
    if plugin_root.exists():
        shutil.rmtree(plugin_root)
    dest = plugin_root / PLUGIN_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def main():
    script_dir = Path(__file__).resolve().parent
    source_dir = script_dir.parent / "cura_plugin" / PLUGIN_NAME / PLUGIN_NAME
    if not (source_dir / "plugin.json").exists():
        print(f"Can't find the plugin source at {source_dir}, is this script still inside the repo?")
        return 1

    base_dir = cura_base_dir(platform.system(), Path.home(), os.environ)
    versions = find_version_dirs(base_dir)
    if not versions:
        print(f"No Cura installation found under {base_dir}.")
        print("Install Cura first, run it once so it creates its config folder, then run this again.")
        return 1

    target = versions[-1]
    if len(versions) > 1:
        found = ", ".join(v.name for v in versions)
        print(f"Found Cura versions: {found}. Installing into the newest ({target.name}).")

    dest = install_plugin(source_dir, target)
    print(f"CuraConnect installed to {dest}")
    print("Restart Cura and it'll show up as a tool on the left toolbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
