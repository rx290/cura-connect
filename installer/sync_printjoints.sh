#!/usr/bin/env bash
# Copy the shared printjoints package into the plugin's vendor folder (pure Python; manifold3d and numpy are
# already vendored/bundled). Run after changing printjoints, then commit the copy.
set -e
SRC="${PRINTJOINTS_SRC:-$HOME/Desktop/Skills/printjoints/src}/printjoints"
DST="$(cd "$(dirname "$0")/.." && pwd)/cura_plugin/CuraConnect/CuraConnect/vendor/printjoints"
rm -rf "$DST"
mkdir -p "$DST"
cp "$SRC"/*.py "$DST"/
echo "vendored $(git -C "$SRC/../.." rev-parse --short HEAD 2>/dev/null || echo unknown) -> $DST"
