# Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
"""
Cura bundles its own frozen Python (3.12 as of Cura 5.13) with its own
isolated set of packages -- manifold3d isn't among them, and pip can't
install into a bundled AppImage-style runtime without root, nor does the
AppImage's own launcher reliably pass through an external PYTHONPATH (its
AppRun wrapper manages environment variables itself). So this vendors the
one compiled dependency (manifold3d) plus its pure-Python chain (numpy-stl,
python-utils, typing-extensions -- numpy itself is already bundled with
Cura) directly inside the plugin folder, which Cura's PluginRegistry already
puts on sys.path when it loads this plugin -- no system files touched, no
environment-variable fragility.

Only actually needed when running inside Cura's bundled Python; if this
package is imported from an environment that already has manifold3d
installed (e.g. this repo's own .venv, used by tests/ and demo.py), the
vendored copy is simply never reached because the already-installed one
resolves first on sys.path.
"""
import sys
import os

_vendor_dir = os.path.join(os.path.dirname(__file__), "..", "vendor")
_vendor_dir = os.path.normpath(_vendor_dir)
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.append(_vendor_dir)
