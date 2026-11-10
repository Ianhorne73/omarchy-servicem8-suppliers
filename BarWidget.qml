import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "servicem8.suppliers"
    property bool opened: false
    property bool setupVisible: false
    property bool createVisible: false
    property var editingSupplier: null
    property bool editReviewVisible: false
    readonly property var editChanges: {
        if (!editingSupplier) return []
        var entries = [["name","supplierName",supplierName.text], ["email","supplierEmail",supplierEmail.text],
            ["phone","supplierPhone",supplierPhone.text], ["address","supplierAddress",supplierAddress.text],
            ["account_number","supplierAccount",supplierAccount.text], ["business_number","supplierBusiness",supplierBusiness.text]]
        return entries.filter(function(e) { return e[2].trim() !== root.editingSupplier.original[e[0]].trim() }).map(function(e) {
            return {label:e[1], before:root.editingSupplier.original[e[0]], after:e[2].trim()}
        })
    }
    property var deletionTarget: null
    readonly property bool deleteVisible: deletionTarget !== null
    property string deleteErrorCode: ""
    property bool duplicateDetected: false
    property string createErrorCode: ""
    property string noticeCode: ""
    readonly property bool busy: fetcher.running || creator.running || deleter.running
    readonly property bool possibleDuplicate: duplicateDetected || (report.suppliers || []).some(function(row) {
        var name = supplierName.text.trim().toLowerCase()
        var email = supplierEmail.text.trim().toLowerCase()
        if (root.editingSupplier && row.uuid === root.editingSupplier.uuid) return false
        var nameChanged = !root.editingSupplier || name !== root.editingSupplier.original.name.trim().toLowerCase()
        var emailChanged = !root.editingSupplier || email !== root.editingSupplier.original.email.trim().toLowerCase()
        return (nameChanged && name !== "" && String(row.name).toLowerCase() === name) || (emailChanged && email !== "" && String(row.email).toLowerCase() === email)
    })
    property var report: ({suppliers: [], error: ""})
    property string query: ""
    property string actionMessage: ""
    readonly property color ink: bar ? bar.foreground : "#eeeeee"
    readonly property string helper: Qt.resolvedUrl("suppliers.py").toString().replace(/^file:\/\//, "")
    readonly property var matches: (report.suppliers || []).filter(function(s) {
        return [s.name, s.email, s.phone, s.address, s.account_number, s.business_number, s.notes].join(" ").toLowerCase().indexOf(query.toLowerCase()) >= 0
    })
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
    component Label: Text {
        textFormat: Text.PlainText
        color: root.ink
        font.family: Qt.application.font.family
        font.pixelSize: 12
        wrapMode: Text.Wrap
    }
    component HeaderButton: Button {
        id: control
        property bool focusable: true
        property bool destructive: false
        signal rightClicked()
        implicitHeight: 32
        implicitWidth: Math.max(32, implicitContentWidth + 22)
        padding: 8
        hoverEnabled: true
        activeFocusOnTab: focusable
        font.family: Qt.application.font.family
        font.pixelSize: 12
        contentItem: Text {
            text: control.text
            textFormat: Text.PlainText
            color: control.destructive ? Commons.Color.urgent : root.ink
            opacity: control.enabled ? 1 : 0.4
            font: control.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 7
            color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, control.down || control.checked ? 0.18 : control.hovered ? 0.12 : 0.06)
            border.width: 1
            border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, control.activeFocus ? 0.65 : 0.12)
            Behavior on color { ColorAnimation { duration: Commons.Style.duration(120) } }
        }
        TapHandler { acceptedButtons: Qt.RightButton; onTapped: control.rightClicked() }
    }
    component HeaderField: TextField {
        id: field
        implicitHeight: 32
        leftPadding: 10
        rightPadding: 10
        color: root.ink
        placeholderTextColor: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.5)
        font.family: Qt.application.font.family
        font.pixelSize: 12
        background: Rectangle {
            radius: 7
            color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.035)
            border.width: 1
            border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, field.activeFocus ? 0.65 : 0.14)
        }
    }
    component HeaderArea: TextArea {
        id: area
        implicitHeight: 64
        padding: 10
        color: root.ink
        font.family: Qt.application.font.family
        font.pixelSize: 12
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.Wrap
        selectByMouse: true
        onTextChanged: { root.invalidateEditConfirmation(); if (text.length > 2048) text = text.slice(0, 2048) }
        background: Rectangle {
            radius: 7
            color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.035)
            border.width: 1
            border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, area.activeFocus ? 0.65 : 0.14)
        }
    }
    function refresh(force) {
        if (root.busy) return
        noticeCode = ""
        fetcher.command = ["python3", helper].concat(force ? ["--force"] : [])
        fetcher.stdinEnabled = true; fetcher.running = true
    }
    function open() { opened = true; refresh(false); Qt.callLater(function() { if (root.deleteVisible) deleteConfirmation.forceActiveFocus(); else if (root.createVisible) supplierName.forceActiveFocus(); else search.forceActiveFocus() }) }
    function close() { invalidateEditConfirmation(); opened = false; apiKey.text = ""; deleteConfirmation.text = ""; if (!deleter.running) cancelDelete() }
    function closeForPopoutSwitch() { close() }
    function toggle() { if (opened) close(); else open() }
    function startCreate() {
        if (root.busy) return
        cancelDelete()
        if (editingSupplier) resetSupplierForm()
        createVisible = true
        setupVisible = false
        createErrorCode = ""
        noticeCode = ""
        Qt.callLater(function() { supplierName.forceActiveFocus() })
    }
    function startEdit(supplier) {
        if (root.busy || !supplier || !supplier.uuid) return
        cancelDelete()
        resetSupplierForm()
        var original = {}
        var fields = ["name", "email", "phone", "address", "account_number", "business_number"]
        for (var i=0; i<fields.length; i++) original[fields[i]] = String(supplier[fields[i]] || "")
        editingSupplier = {uuid:supplier.uuid, original:original}
        supplierName.text = original.name
        supplierEmail.text = original.email
        supplierPhone.text = original.phone
        supplierAddress.text = original.address
        supplierAccount.text = original.account_number
        supplierBusiness.text = original.business_number
        createVisible = true
        setupVisible = false
        noticeCode = ""
        Qt.callLater(function() { supplierName.forceActiveFocus() })
    }
    function startDelete(supplier) {
        invalidateEditConfirmation()
        if (root.busy || !supplier || !supplier.uuid) return
        deletionTarget = {uuid:supplier.uuid, name:supplier.name, email:supplier.email || "", address:supplier.address || ""}
        deleteConfirmation.text = ""
        deleteErrorCode = ""
        createVisible = false
        setupVisible = false
        noticeCode = ""
        Qt.callLater(function() { deleteConfirmation.forceActiveFocus() })
    }
    function cancelDelete() {
        if (deleter.running) return
        deleteConfirmation.text = ""
        deletionTarget = null
        deleteErrorCode = ""
    }
    function confirmDelete() {
        if (root.busy || !deletionTarget || deleteConfirmation.text !== "yes") return
        deleter.payload = JSON.stringify({uuid:deletionTarget.uuid, name:deletionTarget.name, confirmation:deleteConfirmation.text})
        deleteErrorCode = ""
        deleter.stdinEnabled = true
        deleter.running = true
    }
    function invalidateEditConfirmation() {
        editReviewVisible = false
        if (editConfirmation) editConfirmation.text = ""
    }
    function saveSupplier() {
        if (root.busy || !supplierName.text.trim()) return
        if (possibleDuplicate && !allowDuplicate.checked) return
        if (editingSupplier && !editReviewVisible) {
            editReviewVisible = true
            editConfirmation.text = ""
            Qt.callLater(function() { supplierForm.contentY = Math.max(0, supplierForm.contentHeight - supplierForm.height); editConfirmation.forceActiveFocus() })
            return
        }
        if (editingSupplier && editConfirmation.text !== "yes") return
        createErrorCode = ""
        var fields = {name:supplierName.text, email:supplierEmail.text,
            phone:supplierPhone.text, address:supplierAddress.text,
            account_number:supplierAccount.text, business_number:supplierBusiness.text}
        creator.editing = editingSupplier !== null
        creator.command = ["python3", root.helper, creator.editing ? "--edit" : "--create"]
        creator.payload = JSON.stringify(creator.editing ? {uuid:editingSupplier.uuid,
            original:editingSupplier.original, fields:fields, allow_duplicate:allowDuplicate.checked, confirmation:editConfirmation.text} : Object.assign(fields,{allow_duplicate:allowDuplicate.checked}))
        creator.stdinEnabled = true
        creator.running = true
    }
    function resetSupplierForm() {
        invalidateEditConfirmation()
        editingSupplier = null
        supplierName.text = supplierEmail.text = supplierPhone.text = supplierAddress.text = supplierAccount.text = supplierBusiness.text = ""
        allowDuplicate.checked = false
        duplicateDetected = false
        createErrorCode = ""
    }
    function act(kind, value) {
        if (actor.running) return
        actionMessage = ""
        noticeCode = ""
        actor.value = String(value)
        actor.copying = kind === "copy"
        actor.command = ["python3", helper, "--action", kind]
        actor.stdinEnabled = true; actor.running = true
    }
    Process {
        id: fetcher
        property string key: ""
        stdinEnabled: true
        onStarted: { write(key); stdinEnabled = false; key = "" }
        stdout: StdioCollector {
            onStreamFinished: {
                try { root.report = JSON.parse(text) } catch(e) { root.report = Object.assign({}, root.report, {error: "Invalid helper response"}) }
            }
        }
    }
    Process {
        id: actor
        property string value: ""
        property bool copying: false
        stdinEnabled: true
        onStarted: { write(value); stdinEnabled = false; value = "" }
        onExited: function(code, status) { root.actionMessage = code === 0 ? (copying ? strings.t("copied") : "") : strings.t("actionError") }
    }
    Process {
        id: creator
        property bool editing: false
        property string payload: ""
        stdinEnabled: true
        command: ["python3", root.helper, "--create"]
        onStarted: { write(payload); stdinEnabled = false; payload = "" }
        stdout: StdioCollector {
            onStreamFinished: {
                root.invalidateEditConfirmation()
                try {
                    var result = JSON.parse(text)
                    if (result.created === true || result.updated === true) {
                        root.report = result.report
                        search.text = result.supplier.name
                        root.resetSupplierForm()
                        root.createVisible = false
                        root.noticeCode = creator.editing ? (result.refresh_failed ? "editSavedRefreshFailed" : "editSaved") : (result.refresh_failed ? "createSavedRefreshFailed" : "createSaved")
                        list.positionViewAtBeginning()
                    } else {
                        root.createErrorCode = result.error_code || (creator.editing ? "editUncertain" : "createUncertain")
                        root.duplicateDetected = result.duplicate === true
                    }
                } catch(e) { root.createErrorCode = creator.editing ? "editUncertain" : "createUncertain" }
            }
        }
        onExited: function(code, status) { if (code !== 0) { root.invalidateEditConfirmation(); root.createErrorCode = creator.editing ? "editUncertain" : "createUncertain" } }
    }
    Process {
        id: deleter
        property string payload: ""
        stdinEnabled: true
        command: ["python3", root.helper, "--delete"]
        onStarted: { write(payload); stdinEnabled = false; payload = "" }
        stdout: StdioCollector {
            onStreamFinished: {
                deleteConfirmation.text = ""
                try {
                    var result = JSON.parse(text)
                    if (result.deleted === true) {
                        root.report = result.report
                        root.deletionTarget = null
                        root.deleteErrorCode = ""
                        root.noticeCode = result.refresh_failed ? "deleteSavedRefreshFailed" : "deleteSaved"
                        search.forceActiveFocus()
                    } else root.deleteErrorCode = result.error_code || "deleteUncertain"
                } catch(e) { root.deleteErrorCode = "deleteUncertain" }
            }
        }
        onExited: function(code, status) { if (code !== 0) { deleteConfirmation.text = ""; root.deleteErrorCode = "deleteUncertain" } }
    }
    Ui.WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "󰏗"
        tooltipText: strings.t("title")
        onPressed: function(b) { if (b === Qt.RightButton) root.refresh(true); else root.toggle() }
    }
    Ui.KeyboardPanel {
        id: panel
        anchorItem: button
        bar: root.bar
        owner: root
        open: root.opened
        contentWidth: panel.fittedContentWidth(Commons.Style.space(540))
        contentHeight: panel.fittedContentHeight(Commons.Style.space(620))
        focusTarget: root.deleteVisible ? deleteConfirmation : root.createVisible ? supplierName : search
        FocusScope {
            anchors.fill: parent
            Keys.onEscapePressed: { if (root.deleteVisible && !deleter.running) root.cancelDelete(); else root.close() }
            Column {
                id: header
                width: parent.width
                spacing: Commons.Style.space(8)
                Row {
                    spacing: Commons.Style.space(8)
                    Label { text: strings.t("title"); font.pixelSize: 23; font.bold: true }
                    HeaderButton { text: strings.t("refresh"); enabled: !root.busy; focusable: true; onClicked: root.refresh(true) }
                    HeaderButton { text: strings.t("setup"); enabled: !root.busy; focusable: true; onClicked: { root.invalidateEditConfirmation(); root.cancelDelete(); root.createVisible = false; root.setupVisible = !root.setupVisible } }
                    HeaderButton { text: strings.t("newSupplier"); enabled: !root.busy; onClicked: root.startCreate() }
                }
                Label { width: parent.width; text: strings.t("privacy"); opacity: 0.65; font.pixelSize: Commons.Style.space(11) }
                Column {
                    width: parent.width
                    spacing: 5
                    visible: !root.createVisible && !root.deleteVisible && (root.setupVisible || root.report.needs_setup === true)
                    Row {
                        spacing: 7
                        Rectangle { width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: fetcher.running ? root.ink : root.report.connected ? "#70b77e" : Commons.Color.muted; opacity: fetcher.running ? 0.5 : 1 }
                        Label { text: fetcher.running ? strings.t("checking") : root.report.connected ? strings.t("connected") : root.report.needs_setup ? strings.t("notConnected") : strings.t("connectionIssue"); font.bold: true }
                    }
                    Label { width: parent.width; text: strings.t("setupHelp") }
                    HeaderField { id: apiKey; width: parent.width; placeholderText: strings.t("key"); echoMode: TextInput.Password; maximumLength: 4096; color: root.ink }
                    HeaderButton {
                        text: strings.t("connect"); enabled: !root.busy && apiKey.text.trim().length > 0; focusable: true
                        onClicked: { fetcher.key = apiKey.text; apiKey.text = ""; fetcher.command = ["python3", root.helper, "--setup"]; fetcher.stdinEnabled = true; fetcher.running = true }
                    }
                }
                HeaderField { id: search; visible: !root.createVisible && !root.deleteVisible; width: parent.width; placeholderText: strings.t("search"); maximumLength: 256; color: root.ink; onTextChanged: root.query = text }
                Label { width: parent.width; visible: !root.createVisible && !root.deleteVisible && text !== ""; text: root.noticeCode ? strings.t(root.noticeCode) : root.report.error || root.actionMessage; color: root.report.error ? Commons.Color.urgent : root.ink }
                Label { width: parent.width; visible: !root.createVisible && !root.deleteVisible && !!root.report.stale; text: strings.t("offline") }
                Label {
                    width: parent.width
                    visible: !root.createVisible && !root.deleteVisible
                    text: fetcher.running ? strings.t("loading") : strings.tn("count",root.matches.length).arg(Commons.I18n.formatNumber(root.matches.length))
                }
                Label {
                    width: parent.width; visible: !root.createVisible && !root.deleteVisible && !!root.report.updated; opacity: 0.65; font.pixelSize: Commons.Style.space(11)
                    text: root.report.updated ? strings.t("updated").arg(new Date(root.report.updated).toLocaleString(Qt.locale(Commons.I18n.formatLocale), Locale.ShortFormat)) : ""
                }
            }
            Flickable {
                id: supplierForm
                visible: root.createVisible
                anchors { top: header.bottom; topMargin: 14; bottom: parent.bottom; left: parent.left; right: parent.right }
                contentHeight: formFields.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                Column {
                    id: formFields
                    width: supplierForm.width - 12
                    spacing: 8
                    Label { width: parent.width; text: root.editingSupplier ? strings.t("editSupplier") : strings.t("newSupplier"); font.bold: true; font.pixelSize: 16 }
                    Label { width: parent.width; text: root.editingSupplier ? strings.t("editHelp") : strings.t("createHelp"); opacity: 0.7 }
                    Label { text: strings.t("supplierName") }
                    HeaderField { id: supplierName; objectName: "supplierName"; width: parent.width; maximumLength: 200; enabled: !creator.running; onTextChanged: { root.duplicateDetected = false; allowDuplicate.checked = false; root.invalidateEditConfirmation() } }
                    Label { text: strings.t("supplierEmail") }
                    HeaderField { id: supplierEmail; objectName: "supplierEmail"; width: parent.width; maximumLength: 254; enabled: !creator.running; onTextChanged: { root.duplicateDetected = false; allowDuplicate.checked = false; root.invalidateEditConfirmation() } }
                    Label { text: strings.t("supplierPhone") }
                    HeaderField { id: supplierPhone; objectName: "supplierPhone"; width: parent.width; maximumLength: 100; enabled: !creator.running; onTextChanged: root.invalidateEditConfirmation() }
                    Label { text: strings.t("supplierAddress") }
                    HeaderArea { id: supplierAddress; objectName: "supplierAddress"; width: parent.width; enabled: !creator.running }
                    Label { text: strings.t("supplierAccount") }
                    HeaderField { id: supplierAccount; objectName: "supplierAccount"; width: parent.width; maximumLength: 100; enabled: !creator.running; onTextChanged: root.invalidateEditConfirmation() }
                    Label { text: strings.t("supplierBusiness") }
                    HeaderField { id: supplierBusiness; objectName: "supplierBusiness"; width: parent.width; maximumLength: 100; enabled: !creator.running; onTextChanged: root.invalidateEditConfirmation() }
                    Label { width: parent.width; visible: root.possibleDuplicate; text: strings.t("duplicateFound"); color: Commons.Color.urgent }
                    CheckBox {
                        id: allowDuplicate
                        onCheckedChanged: root.invalidateEditConfirmation()
                        visible: root.possibleDuplicate
                        width: parent.width
                        enabled: !creator.running
                        text: strings.t("allowDuplicate")
                        contentItem: Label { text: allowDuplicate.text; leftPadding: allowDuplicate.indicator.width + allowDuplicate.spacing; verticalAlignment: Text.AlignVCenter }
                    }
                    Label { width: parent.width; visible: root.createErrorCode !== ""; text: root.createErrorCode ? strings.t(root.createErrorCode) : ""; color: Commons.Color.urgent }
                    Column {
                        width: parent.width
                        spacing: 8
                        visible: root.editingSupplier !== null && root.editReviewVisible
                        Label { width: parent.width; text: strings.t("editReviewTitle"); font.bold: true; font.pixelSize: 16 }
                        Label { width: parent.width; text: root.editingSupplier ? root.editingSupplier.original.name : ""; font.bold: true }
                        Repeater {
                            model: root.editChanges
                            delegate: Label {
                                required property var modelData
                                width: parent.width
                                text: strings.t("editChange").arg(strings.t(modelData.label)).arg(modelData.before || strings.t("emptyValue")).arg(modelData.after || strings.t("emptyValue"))
                            }
                        }
                        Label { width: parent.width; visible: root.editChanges.length === 0; text: strings.t("noEditChanges") }
                        Label { width: parent.width; text: strings.t("editYesPrompt") }
                        HeaderField { id: editConfirmation; objectName: "editConfirmation"; width: parent.width; maximumLength: 16; placeholderText: "yes"; enabled: !creator.running; selectByMouse: true; Accessible.name: strings.t("editYesPrompt") }
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        HeaderButton { objectName: "saveSupplier"; text: creator.running ? strings.t("savingSupplier") : root.editingSupplier ? (root.editReviewVisible ? strings.t("confirmEdits") : strings.t("reviewEdits")) : root.createErrorCode ? strings.t("retrySave") : strings.t("saveSupplier"); enabled: !root.busy && supplierName.text.trim() !== "" && (!root.possibleDuplicate || allowDuplicate.checked) && (!root.editingSupplier || !root.editReviewVisible || editConfirmation.text === "yes"); onClicked: root.saveSupplier() }
                        HeaderButton { text: root.editingSupplier ? strings.t("cancelEdit") : strings.t("backToSuppliers"); enabled: !creator.running; onClicked: { if (root.editingSupplier) root.resetSupplierForm(); root.createVisible = false; search.forceActiveFocus() } }
                    }
                }
            }
            Flickable {
                id: deleteForm
                visible: root.deleteVisible
                anchors { top: header.bottom; topMargin: 14; bottom: parent.bottom; left: parent.left; right: parent.right }
                contentHeight: deleteFields.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                Column {
                    id: deleteFields
                    width: deleteForm.width - 12
                    spacing: 12
                    Label { text: strings.t("deleteTitle"); font.pixelSize: 16; font.bold: true; color: Commons.Color.urgent }
                    Label { width: parent.width; text: root.deletionTarget ? root.deletionTarget.name : ""; font.pixelSize: 16; font.bold: true }
                    Label { width: parent.width; text: root.deletionTarget ? [root.deletionTarget.email,root.deletionTarget.address].filter(function(v) { return !!v }).join("\n") : ""; visible: text !== "" }
                    Label { width: parent.width; text: strings.t("deleteHelp") }
                    Label { width: parent.width; text: strings.t("deletePrompt") }
                    HeaderField { id: deleteConfirmation; objectName: "deleteConfirmation"; width: parent.width; maximumLength: 16; enabled: !deleter.running; placeholderText: "yes"; selectByMouse: true; Accessible.name: strings.t("deletePrompt") }
                    Label { width: parent.width; visible: root.deleteErrorCode !== ""; text: root.deleteErrorCode ? strings.t(root.deleteErrorCode) : ""; color: Commons.Color.urgent }
                    Flow {
                        width: parent.width
                        spacing: 8
                        HeaderButton { objectName: "confirmDelete"; destructive: true; text: deleter.running ? strings.t("deleting") : strings.t("deleteConfirm"); enabled: !root.busy && deleteConfirmation.text === "yes"; onClicked: root.confirmDelete() }
                        HeaderButton { text: strings.t("cancelDelete"); enabled: !deleter.running; onClicked: { root.cancelDelete(); search.forceActiveFocus() } }
                    }
                }
            }
            ListView {
                id: list
                visible: !root.createVisible && !root.deleteVisible
                anchors.top: header.bottom
                anchors.topMargin: 14
                anchors.bottom: parent.bottom
                boundsBehavior: Flickable.StopAtBounds
                width: parent.width
                clip: true
                spacing: Commons.Style.space(10)
                model: root.matches
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: supplierCard
                    required property var modelData
                    width: list.width
                    height: details.implicitHeight + 24
                    radius: Commons.Style.space(8)
                    color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.06)
                    Column {
                        id: details
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                        spacing: 5
                        Label { width: parent.width; text: supplierCard.modelData.name; font.bold: true; font.pixelSize: 16 }
                        Repeater {
                            model: [supplierCard.modelData.email, supplierCard.modelData.phone, supplierCard.modelData.address, supplierCard.modelData.account_number ? strings.t("account").arg(supplierCard.modelData.account_number) : "", supplierCard.modelData.business_number ? strings.t("business").arg(supplierCard.modelData.business_number) : "", supplierCard.modelData.website, supplierCard.modelData.notes].filter(function(v) { return !!v })
                            delegate: Label { required property string modelData; width: details.width; text: modelData }
                        }
                        Flow {
                            width: parent.width; spacing: Commons.Style.space(5)
                            HeaderButton { text: strings.t("email"); visible: !!supplierCard.modelData.email; focusable: true; onClicked: root.act("email",supplierCard.modelData.email); onRightClicked: root.act("copy",supplierCard.modelData.email) }
                            HeaderButton { text: strings.t("website"); visible: !!supplierCard.modelData.website; focusable: true; onClicked: root.act("website",supplierCard.modelData.website) }
                            HeaderButton { text: strings.t("websearch"); visible: !supplierCard.modelData.website; focusable: true; onClicked: root.act("website","https://www.google.com/search?q=" + encodeURIComponent(supplierCard.modelData.name + " " + supplierCard.modelData.address)) }
                            HeaderButton { text: strings.t("map"); visible: !!supplierCard.modelData.address; focusable: true; onClicked: root.act("map",supplierCard.modelData.address) }
                            HeaderButton { text: strings.t("edit"); enabled: !root.busy && !!supplierCard.modelData.uuid; onClicked: root.startEdit(supplierCard.modelData) }
                            HeaderButton { text: strings.t("delete"); destructive: true; enabled: !root.busy && !!supplierCard.modelData.uuid; onClicked: root.startDelete(supplierCard.modelData) }
                            HeaderButton { text: strings.t("copy"); focusable: true; onClicked: root.act("copy",[supplierCard.modelData.name,supplierCard.modelData.email,supplierCard.modelData.phone,supplierCard.modelData.address,supplierCard.modelData.account_number,supplierCard.modelData.business_number,supplierCard.modelData.website,supplierCard.modelData.notes].filter(function(v) { return !!v }).join("\n")) }
                        }
                    }
                }
            }
        }
    }
}
