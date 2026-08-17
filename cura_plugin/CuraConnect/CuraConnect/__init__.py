# Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
from . import CuraConnectTool

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("cura")


def getMetaData():
    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "Cura Connect"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Split a model with real mechanical connectors"),
            "icon": "Link",
            "tool_panel": "CuraConnectPanel.qml",
            "weight": 10,
        },
    }


def register(app):
    return {"tool": CuraConnectTool.CuraConnectTool()}
