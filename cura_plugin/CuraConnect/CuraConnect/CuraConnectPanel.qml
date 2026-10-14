// Copyright (c) 2026, cura-connect, MIT licensed, see the repo's LICENSE file.
import QtQuick 2.15
import QtQuick.Controls 2.15
import UM 1.7 as UM
import Cura 1.1 as Cura

Item
{
    id: base
    width: UM.Theme.getSize("setting_control").width * 2 + margin
    height: items.height
    property real margin: UM.Theme.getSize("default_margin").width
    property real labelWidth: width * 0.32
    property real controlHeight: UM.Theme.getSize("setting_control").height
    property bool pendingCut: false
    property bool busy: pendingCut || UM.Controller.properties.getValue("Busy") == true
    UM.I18nCatalog { id: catalog; name: "cura" }

    // Let the disabled state paint before the existing synchronous cut starts.
    Timer
    {
        id: cutTimer
        interval: 100
        onTriggered:
        {
            UM.Controller.triggerAction("performCut")
            base.pendingCut = false
        }
    }

    Column
    {
        id: items
        width: parent.width
        spacing: UM.Theme.getSize("default_margin").height
        enabled: !base.busy

        UM.Label { text: catalog.i18nc("@label", "1  Cut plane"); font.bold: true }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Axis")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            Cura.ComboBox
            {
                width: parent.width - base.labelWidth - base.margin
                height: base.controlHeight
                model: ["X", "Y", "Z"]
                currentIndex: model.indexOf(UM.Controller.properties.getValue("CutAxis"))
                onActivated: UM.Controller.setProperty("CutAxis", model[currentIndex])
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Position")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: planePositionField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("PlanePosition")
                validator: UM.FloatValidator { maxBeforeDecimal: 4; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("PlanePosition", text.replace(",", "."))
            }
        }

        Slider
        {
            id: positionSlider
            width: parent.width
            from: UM.Controller.properties.getValue("PlaneMinimum")
            to: UM.Controller.properties.getValue("PlaneMaximum")
            value: UM.Controller.properties.getValue("PlanePosition")
            enabled: to > from
            onMoved: UM.Controller.setProperty("PlanePosition", value)
            Accessible.name: catalog.i18nc("@label", "Cut plane position")
            background: Rectangle
            {
                x: positionSlider.leftPadding
                y: positionSlider.topPadding + positionSlider.availableHeight / 2 - height / 2
                width: positionSlider.availableWidth
                height: UM.Theme.getSize("slider_widget_groove").height
                radius: height / 2
                color: UM.Theme.getColor("lining")
                Rectangle
                {
                    width: parent.width * positionSlider.visualPosition
                    height: parent.height
                    radius: parent.radius
                    color: UM.Theme.getColor("primary")
                }
            }
            handle: Rectangle
            {
                x: positionSlider.leftPadding + positionSlider.visualPosition * (positionSlider.availableWidth - width)
                y: positionSlider.topPadding + positionSlider.availableHeight / 2 - height / 2
                implicitWidth: UM.Theme.getSize("slider_widget_handle").width
                implicitHeight: UM.Theme.getSize("slider_widget_handle").height
                radius: width / 2
                color: UM.Theme.getColor(positionSlider.enabled ? "primary" : "text_disabled")
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Tilt")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: tiltAngleField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "°"
                text: UM.Controller.properties.getValue("TiltAngle")
                validator: UM.FloatValidator { maxBeforeDecimal: 2; maxAfterDecimal: 1 }
                onEditingFinished: UM.Controller.setProperty("TiltAngle", text.replace(",", "."))
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Plane size")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: planeSizeField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("PlaneSize")
                validator: UM.FloatValidator { maxBeforeDecimal: 4; maxAfterDecimal: 1 }
                onEditingFinished: UM.Controller.setProperty("PlaneSize", text.replace(",", "."))
            }
        }

        Rectangle { width: parent.width; height: 1; color: UM.Theme.getColor("lining") }
        UM.Label { text: catalog.i18nc("@label", "2  Connector"); font.bold: true }
        // Wrap whole buttons at narrow panel widths, never their labels.
        Flow
        {
            width: parent.width
            spacing: base.margin
            Repeater
            {
                model: [
                    { key: "dovetail", label: "Dovetail", tip: "Slide the dovetail sideways into its matching groove." },
                    { key: "plug", label: "Plug", tip: "Push the plug straight into its socket." },
                    { key: "dowel", label: "Dowel", tip: "Insert the loose dowel into both matching holes." },
                    { key: "snap", label: "Snap", tip: "Press the halves together until the snap catches." },
                    { key: "twist", label: "Twist", tip: "Push the lugs into the slots, then twist to lock." },
                    { key: "thread", label: "Thread", tip: "Turn the halves to screw the threaded joint together." },
                    { key: "squeeze", label: "Squeeze", tip: "Squeeze the flexible fingers and push into the socket." }
                ]
                Cura.SecondaryButton
                {
                    text: catalog.i18nc("@action:button", modelData.label)
                    tooltip: catalog.i18nc("@tooltip", modelData.tip)
                    checkable: true
                    checked: UM.Controller.properties.getValue("ConnectorType") === modelData.key
                    color: UM.Theme.getColor(checked ? "primary_button" : "secondary_button")
                    textColor: UM.Theme.getColor(checked ? "primary_button_text" : "secondary_button_text")
                    hoverColor: UM.Theme.getColor(checked ? "primary_button_hover" : "secondary_button_hover")
                    textHoverColor: textColor
                    onClicked: UM.Controller.setProperty("ConnectorType", modelData.key)
                }
            }
        }
        UM.CheckBox
        {
            text: catalog.i18nc("@option:check", "Vase mode")
            checked: UM.Controller.properties.getValue("VaseMode") == true
            onClicked: UM.Controller.setProperty("VaseMode", checked)
            UM.ToolTip
            {
                text: catalog.i18nc("@tooltip", "Size connectors for this model's spiralized wall thickness.")
                visible: parent.hovered
            }
        }
        Rectangle { width: parent.width; height: 1; color: UM.Theme.getColor("lining") }
        UM.Label { text: catalog.i18nc("@label", "3  Size"); font.bold: true }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Width")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: widthField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Width")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Width", text.replace(",", "."))
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Depth")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: depthField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Depth")
                validator: UM.FloatValidator { maxBeforeDecimal: 3; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Depth", text.replace(",", "."))
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Tolerance")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: toleranceField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.Controller.properties.getValue("Tolerance")
                validator: UM.FloatValidator { maxBeforeDecimal: 2; maxAfterDecimal: 2 }
                onEditingFinished: UM.Controller.setProperty("Tolerance", text.replace(",", "."))
            }
        }
        Row
        {
            width: parent.width
            spacing: base.margin
            UM.Label
            {
                text: catalog.i18nc("@label", "Count")
                width: base.labelWidth
                height: base.controlHeight
                verticalAlignment: Text.AlignVCenter
            }
            UM.TextFieldWithUnit
            {
                id: connectorCountField
                width: parent.width - base.labelWidth - base.margin
                height: UM.Theme.getSize("setting_control").height
                unit: ""
                text: UM.Controller.properties.getValue("ConnectorCount")
                validator: UM.FloatValidator { maxBeforeDecimal: 1; maxAfterDecimal: 0 }
                onEditingFinished: UM.Controller.setProperty("ConnectorCount", text)
            }
        }

        Rectangle { width: parent.width; height: 1; color: UM.Theme.getColor("lining") }
        Row
        {
            width: parent.width
            spacing: base.margin
            Cura.SecondaryButton
            {
                width: (parent.width - base.margin) / 2
                fixedWidthMode: true
                text: catalog.i18nc("@action:button", "Preview")
                tooltip: catalog.i18nc("@tooltip", "Show the cut plane on the selected model.")
                onClicked: UM.Controller.triggerAction("previewCut")
            }
            Cura.PrimaryButton
            {
                width: (parent.width - base.margin) / 2
                fixedWidthMode: true
                text: base.busy ? catalog.i18nc("@action:button", "Cutting…") : catalog.i18nc("@action:button", "Cut")
                onClicked: { base.pendingCut = true; cutTimer.start() }
            }
        }
        UM.Label
        {
            width: parent.width
            wrapMode: Text.WordWrap
            text: base.busy ? catalog.i18nc("@info", "Cutting model…") : UM.Controller.properties.getValue("Status")
            color: UM.Theme.getColor("text")
            Accessible.role: Accessible.StaticText
        }
    }
}
