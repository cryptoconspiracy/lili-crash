import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var usage: ({})
    property var programs: []
    property int pending: 0
    property string crashError: ""

    readonly property var agentNames: ({
        claude: "Claude Code", codex: "Codex", opencode: "OpenCode", gemini: "Gemini CLI",
        agy: "Antigravity CLI", copilot: "GitHub Copilot CLI", cursor: "Cursor CLI", grok: "Grok CLI"
    })
    readonly property string agent: Plasmoid.configuration.agent
    readonly property var current: usage[agent] || {}
    readonly property int session: current.session ? current.session.percent : -1
    readonly property url avatar: Qt.resolvedUrl("../images/" + Plasmoid.configuration.avatar + ".png")
    readonly property string usageScript: Qt.resolvedUrl("../code/usage.py").toString().replace("file://", "")

    function modelOf(name) {
        const chosen = Plasmoid.configuration[name + "_model"]
        const model = chosen && chosen !== "default" ? chosen : (usage[name] || {}).model
        if (!model) return i18n("default model")
        return model.charAt(0).toUpperCase() + model.slice(1)
    }

    function errorText(code) {
        switch (code) {
        case "not_installed": return i18n("Not installed")
        case "no_login": return i18n("Not logged in")
        case "expired": return i18n("Login expired; open the agent once to renew it")
        case "offline": return i18n("Can't reach the server")
        case "http": return i18n("The server refused the request")
        }
        return ""
    }

    function severity(percent) {
        if (percent >= 95) return Kirigami.Theme.negativeTextColor
        if (percent >= 80) return Kirigami.Theme.neutralTextColor
        return Kirigami.Theme.highlightColor
    }

    function resetText(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        const time = d.toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
        if (d.toDateString() === new Date().toDateString()) return i18n("resets today at %1", time)
        return i18n("resets %1 at %2", d.toLocaleDateString(Qt.locale(), "ddd d"), time)
    }

    function crashWhen(seconds) {
        const d = new Date(seconds * 1000)
        const time = d.toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
        const today = new Date()
        const yesterday = new Date(today.getTime() - 86400000)
        if (d.toDateString() === today.toDateString()) return i18n("today at %1", time)
        if (d.toDateString() === yesterday.toDateString()) return i18n("yesterday at %1", time)
        return i18n("%1 at %2", d.toLocaleDateString(Qt.locale(), Locale.ShortFormat), time)
    }

    function quote(text) {
        return "'" + String(text).replace(/'/g, "'\\''") + "'"
    }

    function mark(exe, state) {
        crashes.run("lili-crash mark " + quote(exe) + " " + state + " && lili-crash list")
    }

    function diagnose(pids) {
        // setsid detaches the terminal, so closing the popup doesn't take it down.
        crashes.run("setsid -f lili-crash diagnose " + pids.join(" ") + " >/dev/null 2>&1; sleep 1; lili-crash list")
        root.expanded = false
    }

    function diagnoseAll() {
        diagnose(programs.filter(p => p.state === "new").map(p => p.last.pid))
    }

    function saveSettings() {
        const c = Plasmoid.configuration
        const keys = ["avatar", "agent", "terminal", "shell"].concat(
            ["claude", "codex", "opencode", "gemini", "copilot", "cursor"].map(a => a + "_model"))
        settings.run(keys.map(k => "lili-crash config set " + k + " " + quote(c[k])).join(" && "))
    }

    Plasmoid.icon: avatar
    Plasmoid.status: pending > 0 ? PlasmaCore.Types.NeedsAttentionStatus : PlasmaCore.Types.ActiveStatus

    toolTipMainText: "Lili"
    toolTipSubText: {
        const lines = []
        for (const name of ["claude", "codex"]) {
            const u = usage[name]
            if (!u || u.error === "not_installed") continue
            if (u.session)
                lines.push(i18n("%1 (%2): %3% of the session, %4% of the week",
                                agentNames[name], modelOf(name), u.session.percent, u.week ? u.week.percent : 0))
            else
                lines.push(agentNames[name] + ": " + errorText(u.error))
        }
        if (!usage[agent])
            lines.push(i18n("Diagnoses with %1 (%2)", agentNames[agent] || agent, modelOf(agent)))
        lines.push(pending === 0 ? i18n("No new crashes") : i18np("1 new crash", "%1 new crashes", pending))
        return lines.join("\n")
    }

    onExpandedChanged: () => { if (root.expanded) { crashes.run("lili-crash list"); usageSource.refresh() } }

    // The commands live in ~/.local/bin, which plasmashell doesn't always have on PATH.
    component Shell: P5Support.DataSource {
        engine: "executable"
        function run(command) {
            connectSource("PATH=\"$HOME/.local/bin:$PATH\"; " + command)
        }
    }

    Shell {
        id: usageSource
        function refresh() { run("python3 " + root.quote(root.usageScript)) }
        onNewData: (source, data) => {
            disconnectSource(source)
            try { root.usage = JSON.parse(data.stdout) } catch (e) {}
        }
    }

    Shell {
        id: crashes
        onNewData: (source, data) => {
            disconnectSource(source)
            try {
                const found = JSON.parse(data.stdout)
                root.programs = found.programs
                root.pending = found.pending
                root.crashError = ""
            } catch (e) {
                root.crashError = (data.stderr || data.stdout || "").trim()
            }
        }
    }

    Shell {
        id: settings
        onNewData: (source) => disconnectSource(source)
    }

    Connections {
        target: Plasmoid.configuration
        function onValueChanged() { root.saveSettings() }
    }

    Component.onCompleted: saveSettings()

    // The usage endpoints are undocumented; every 5 minutes is plenty for numbers that move slowly.
    Timer {
        interval: 5 * 60 * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: usageSource.refresh()
    }

    Timer {
        interval: 60 * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: crashes.run("lili-crash list")
    }

    compactRepresentation: MouseArea {
        id: compact
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        Kirigami.Icon {
            id: face
            anchors.fill: parent
            source: root.avatar
            active: compact.containsMouse
        }

        Rectangle {
            visible: root.session >= 0
            anchors.right: face.right
            anchors.bottom: face.bottom
            anchors.margins: -1
            height: Math.max(9, Math.round(face.height * 0.46))
            width: Math.max(height, percent.implicitWidth + height * 0.4)
            radius: height / 2
            color: root.session >= 80 ? root.severity(root.session) : Kirigami.Theme.backgroundColor
            border.width: 1
            border.color: root.session >= 80 ? "transparent" : Kirigami.Theme.highlightColor
            opacity: root.current.stale ? 0.6 : 1

            PlasmaComponents3.Label {
                id: percent
                anchors.centerIn: parent
                text: root.session
                font.pixelSize: parent.height * 0.72
                font.bold: true
                color: root.session >= 80 ? "white" : Kirigami.Theme.textColor
            }
        }

        Rectangle {
            visible: root.pending > 0
            anchors.right: face.right
            anchors.top: face.top
            width: Math.max(6, Math.round(face.height * 0.28))
            height: width
            radius: width / 2
            color: Kirigami.Theme.negativeTextColor
            border.width: 1
            border.color: Kirigami.Theme.backgroundColor
        }
    }

    component UsageCard: ColumnLayout {
        id: card
        required property string name
        readonly property var info: root.usage[name] || {}
        visible: card.info.error !== "not_installed" && root.usage[name] !== undefined
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            PlasmaExtras.Heading {
                level: 5
                text: root.agentNames[card.name]
                Layout.fillWidth: true
            }
            PlasmaComponents3.Label {
                text: root.modelOf(card.name) + (card.info.plan ? " · " + card.info.plan : "")
                opacity: 0.7
                font: Kirigami.Theme.smallFont
            }
        }

        Repeater {
            model: [
                { label: i18n("Session (5 h)"), window: card.info.session },
                { label: i18n("Week"), window: card.info.week }
            ]
            delegate: ColumnLayout {
                required property var modelData
                visible: !!modelData.window
                Layout.fillWidth: true
                spacing: 2

                RowLayout {
                    Layout.fillWidth: true
                    PlasmaComponents3.Label { text: modelData.label; Layout.fillWidth: true }
                    PlasmaComponents3.Label {
                        text: modelData.window ? modelData.window.percent + "%" : ""
                        color: modelData.window && modelData.window.percent >= 80 ? root.severity(modelData.window.percent) : Kirigami.Theme.textColor
                        font.bold: true
                    }
                }
                PlasmaComponents3.ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: 100
                    value: modelData.window ? Math.min(modelData.window.percent, 100) : 0
                }
                PlasmaComponents3.Label {
                    text: modelData.window ? root.resetText(modelData.window.resets) : ""
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
        }

        PlasmaComponents3.Label {
            visible: !!card.info.error
            text: root.errorText(card.info.error)
            color: Kirigami.Theme.neutralTextColor
            font: Kirigami.Theme.smallFont
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    readonly property var stateStyles: ({
        new: { label: i18n("New"), color: Kirigami.Theme.negativeTextColor },
        diagnosed: { label: i18n("Diagnosed"), color: Kirigami.Theme.neutralTextColor },
        resolved: { label: i18n("Resolved"), color: Kirigami.Theme.positiveTextColor },
        ignored: { label: i18n("Ignored"), color: Kirigami.Theme.disabledTextColor }
    })

    fullRepresentation: PlasmaExtras.Representation {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 26
        Layout.preferredHeight: Kirigami.Units.gridUnit * 32
        Layout.minimumWidth: Kirigami.Units.gridUnit * 20
        collapseMarginsHint: true

        header: PlasmaExtras.PlasmoidHeading {
            RowLayout {
                anchors.fill: parent
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Icon {
                    source: root.avatar
                    Layout.preferredWidth: Kirigami.Units.iconSizes.large
                    Layout.preferredHeight: Kirigami.Units.iconSizes.large
                }
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    PlasmaExtras.Heading { level: 3; text: "Lili" }
                    PlasmaComponents3.Label {
                        opacity: 0.7
                        text: root.pending === 0 ? i18n("All caught up")
                              : i18np("1 program needs a look", "%1 programs need a look", root.pending)
                    }
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    onClicked: { crashes.run("lili-crash list"); usageSource.refresh() }
                    PlasmaComponents3.ToolTip { text: i18n("Refresh") }
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "configure"
                    onClicked: Plasmoid.internalAction("configure").trigger()
                    PlasmaComponents3.ToolTip { text: i18n("Settings") }
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.largeSpacing

            UsageCard { name: "claude"; Layout.fillWidth: true }
            UsageCard { name: "codex"; Layout.fillWidth: true }

            Kirigami.Separator { Layout.fillWidth: true }

            RowLayout {
                Layout.fillWidth: true
                PlasmaExtras.Heading { level: 4; text: i18n("Crashes"); Layout.fillWidth: true }
                PlasmaComponents3.Button {
                    visible: root.pending > 0
                    icon.name: "tools-wizard"
                    text: root.pending > 1 ? i18n("Diagnose all (%1)", root.pending) : i18n("Diagnose")
                    onClicked: root.diagnoseAll()
                }
            }

            PlasmaComponents3.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ListView {
                    id: list
                    model: root.programs
                    spacing: Kirigami.Units.smallSpacing
                    clip: true

                    PlasmaExtras.PlaceholderMessage {
                        anchors.centerIn: parent
                        width: parent.width - Kirigami.Units.gridUnit * 2
                        visible: list.count === 0
                        iconName: root.crashError ? "dialog-error" : "checkmark"
                        text: root.crashError ? i18n("Couldn't read the crash history") : i18n("Nothing has crashed")
                        explanation: root.crashError
                    }

                    delegate: PlasmaExtras.ExpandableListItem {
                        required property var modelData
                        readonly property var style: root.stateStyles[modelData.state] || root.stateStyles["new"]

                        icon: modelData.icon
                        title: modelData.name
                        subtitle: (modelData.count > 1 ? i18n("%1 times, last %2", modelData.count, root.crashWhen(modelData.last.time))
                                                        : root.crashWhen(modelData.last.time))
                                  + " · " + style.label
                        defaultActionButtonAction: QQC2.Action {
                            icon.name: "tools-wizard"
                            text: modelData.state === "new" ? i18n("Diagnose") : i18n("Diagnose again")
                            onTriggered: root.diagnose([modelData.last.pid])
                        }

                        customExpandedViewContent: ColumnLayout {
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                text: modelData.last.reason + " (" + modelData.last.signal + ")"
                                wrapMode: Text.WordWrap
                            }
                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                visible: modelData.summary !== ""
                                text: modelData.summary
                                wrapMode: Text.WordWrap
                                font.italic: true
                            }
                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                text: modelData.exe
                                opacity: 0.6
                                font: Kirigami.Theme.smallFont
                                elide: Text.ElideMiddle
                            }
                            RowLayout {
                                Layout.alignment: Qt.AlignRight
                                PlasmaComponents3.ToolButton {
                                    visible: modelData.state !== "resolved"
                                    icon.name: "checkmark"
                                    text: i18n("Resolved")
                                    onClicked: root.mark(modelData.exe, "resolved")
                                }
                                PlasmaComponents3.ToolButton {
                                    visible: modelData.state !== "ignored"
                                    icon.name: "view-hidden"
                                    text: i18n("Ignore")
                                    onClicked: root.mark(modelData.exe, "ignored")
                                }
                                PlasmaComponents3.ToolButton {
                                    visible: modelData.state === "resolved" || modelData.state === "ignored"
                                    icon.name: "edit-undo"
                                    text: i18n("Reopen")
                                    onClicked: root.mark(modelData.exe, "new")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
