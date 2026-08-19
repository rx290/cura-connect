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

    Column
    {
        id: items
        spacing: UM.Theme.getSize("default_margin").height

        UM.Label
        {
            text: catalog.i18nc("@label", "A cut plane is suggested automatically. Drag the model or a colored arrow to adjust it, click an arrow to change axis, dial in a tilt if you want an angled cut, then press Cut.")
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
            spacing: UM.Theme.getSize("narrow_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Cut axis")
                width: UM.Theme.getSize("setting_control").width
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.Label
            {
                text: UM.Controller.properties.getValue("CutAxis")
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
                font.bold: true
            }
            Rectangle { width: 12; height: 12; radius: 2; color: UM.Theme.getColor("x_axis"); anchors.verticalCenter: parent.verticalCenter }
            UM.Label { text: "X"; height: UM.Theme.getSize("setting_control").height; verticalAlignment: Text.AlignVCenter }
            Rectangle { width: 12; height: 12; radius: 2; color: UM.Theme.getColor("y_axis"); anchors.verticalCenter: parent.verticalCenter }
            UM.Label { text: "Y"; height: UM.Theme.getSize("setting_control").height; verticalAlignment: Text.AlignVCenter }
            Rectangle { width: 12; height: 12; radius: 2; color: UM.Theme.getColor("z_axis"); anchors.verticalCenter: parent.verticalCenter }
            UM.Label { text: "Z"; height: UM.Theme.getSize("setting_control").height; verticalAlignment: Text.AlignVCenter }
            UM.Label
            {
                text: catalog.i18nc("@label", "Tilt")
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: tiltAngleField
                width: UM.Theme.getSize("setting_control").width * 0.75
                height: UM.Theme.getSize("setting_control").height
                unit: "°"
                text: UM.Controller.properties.getValue("TiltAngle")
                validator: UM.FloatValidator { maxBeforeDecimal: 2; maxAfterDecimal: 1 }
                onEditingFinished: UM.Controller.setProperty("TiltAngle", text.replace(",", "."))
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("narrow_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Width")
                width: UM.Theme.getSize("setting_control").width / 2
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: widthField
                width: UM.Theme.getSize("setting_control").width * 0.75
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Width")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Width", text.replace(",", "."))
            }
            UM.Label
            {
                text: catalog.i18nc("@label", "Depth")
                width: UM.Theme.getSize("setting_control").width / 2
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: depthField
                width: UM.Theme.getSize("setting_control").width * 0.75
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Depth")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Depth", text.replace(",", "."))
            }
            UM.Label
            {
                text: catalog.i18nc("@label", "Count")
                width: UM.Theme.getSize("setting_control").width / 2
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: connectorCountField
                width: UM.Theme.getSize("setting_control").width * 0.5
                height: UM.Theme.getSize("setting_control").height
                unit: ""
                text: UM.Controller.properties.getValue("ConnectorCount")
                validator: UM.FloatValidator { maxBeforeDecimal: 1; maxAfterDecimal: 0 }
                onEditingFinished: UM.Controller.setProperty("ConnectorCount", text)
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

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            UM.Label
            {
                text: catalog.i18nc("@label", "Plane pos.")
                width: UM.Theme.getSize("setting_control").width / 2
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: planePositionField
                width: UM.Theme.getSize("setting_control").width * 0.75
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("PlanePosition")
                validator: UM.FloatValidator { maxBeforeDecimal: 4; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("PlanePosition", text.replace(",", "."))
            }
            UM.Label
            {
                text: catalog.i18nc("@label", "size")
                width: UM.Theme.getSize("setting_control").width / 3
                height: UM.Theme.getSize("setting_control").height
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: planeSizeField
                width: UM.Theme.getSize("setting_control").width * 0.75
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("PlaneSize")
                validator: UM.FloatValidator { maxBeforeDecimal: 4; maxAfterDecimal: 1 }
                onEditingFinished: UM.Controller.setProperty("PlaneSize", text.replace(",", "."))
            }
            Button
            {
                id: cutButton
                text: catalog.i18nc("@action:button", "Cut")
                height: UM.Theme.getSize("setting_control").height
                onClicked: UM.Controller.triggerAction("performCut")
            }
        }
    }
}
