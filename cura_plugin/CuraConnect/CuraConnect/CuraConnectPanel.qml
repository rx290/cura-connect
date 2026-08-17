// Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
import QtQuick 2.15
import QtQuick.Controls 2.15

import UM 1.7 as UM

Item
{
    id: base
    width: childrenRect.width
    height: childrenRect.height
    UM.I18nCatalog { id: catalog; name: "cura" }

    property var connectorTypes: ["dovetail", "plug", "dowel", "snap"]
    property var axes: ["Z", "X", "Y"]

    Column
    {
        id: items
        spacing: UM.Theme.getSize("default_margin").height

        UM.Label
        {
            text: catalog.i18nc("@label", "Click on the selected model to cut it at that point.")
            width: UM.Theme.getSize("setting_control").width * 2
            wrapMode: Text.WordWrap
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Connector")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            ComboBox
            {
                id: connectorTypeCombo
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                model: base.connectorTypes
                currentIndex: base.connectorTypes.indexOf(UM.Controller.properties.getValue("ConnectorType"))
                onActivated: UM.Controller.setProperty("ConnectorType", base.connectorTypes[currentIndex])
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Cut axis")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            ComboBox
            {
                id: cutAxisCombo
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                model: base.axes
                currentIndex: base.axes.indexOf(UM.Controller.properties.getValue("CutAxis"))
                onActivated: UM.Controller.setProperty("CutAxis", base.axes[currentIndex])
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Width")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: widthField
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Width")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Width", text.replace(",", "."))
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Depth")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: depthField
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Depth")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Depth", text.replace(",", "."))
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Tolerance")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: toleranceField
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Tolerance")
                validator: UM.FloatValidator { maxBeforeDecimal: 2; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Tolerance", text.replace(",", "."))
            }
        }
    }
}
