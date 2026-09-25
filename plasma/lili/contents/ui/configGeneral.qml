import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasma5support as P5Support

KCM.SimpleKCM {
    id: page

    property string cfg_avatar
    property string cfg_agent
    property string cfg_claude_model
    property string cfg_codex_model
    property string cfg_opencode_model
    property string cfg_gemini_model
    property string cfg_copilot_model
    property string cfg_cursor_model
    property string cfg_terminal
    property string cfg_shell
    property string cfg_avatarDefault
    property string cfg_agentDefault
    property string cfg_claude_modelDefault
    property string cfg_codex_modelDefault
    property string cfg_opencode_modelDefault
    property string cfg_gemini_modelDefault
    property string cfg_copilot_modelDefault
    property string cfg_cursor_modelDefault
    property string cfg_terminalDefault
    property string cfg_shellDefault

    property var agents: []
    property var installedTerminals: []
    property var distro: ({})

    P5Support.DataSource {
        id: shell
        engine: "executable"
        onNewData: (source, data) => {
            disconnectSource(source)
            try {
                const found = JSON.parse(data.stdout)
                page.agents = found.agents
                page.installedTerminals = found.terminals
                page.distro = found.distro
            } catch (e) {}
        }
        function run(command) {
            connectSource("PATH=\"$HOME/.local/bin:$PATH\"; " + command)
        }
    }

    // Installing happens in a terminal the user watches; poll so the page notices when it's done.
    Timer {
        interval: 4000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: shell.run("lili-crash config")
    }

    component AvatarChoice: QQC2.AbstractButton {
        required property string name
        checkable: true
        checked: page.cfg_avatar === name
        onClicked: page.cfg_avatar = name
        implicitWidth: Kirigami.Units.gridUnit * 4
        implicitHeight: implicitWidth
        padding: 4
        hoverEnabled: true

        contentItem: Image {
            source: Qt.resolvedUrl("../images/" + parent.name + ".png")
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }
        background: Rectangle {
            radius: width / 2
            color: "transparent"
            border.width: parent.checked ? 3 : (parent.hovered ? 1 : 0)
            border.color: Kirigami.Theme.highlightColor
        }
    }

    Kirigami.FormLayout {
        RowLayout {
            Kirigami.FormData.label: i18n("Avatar:")
            spacing: Kirigami.Units.largeSpacing
            AvatarChoice { name: "lili1" }
            AvatarChoice { name: "lili2" }
            AvatarChoice { name: "lili3" }
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("AI agents")
        }

        GridLayout {
            Kirigami.FormData.label: i18n("Diagnose crashes with:")
            Kirigami.FormData.labelAlignment: Qt.AlignTop
            columns: 3
            columnSpacing: Kirigami.Units.largeSpacing

            Repeater {
                model: page.agents
                delegate: QQC2.RadioButton {
                    required property var modelData
                    required property int index
                    Layout.row: index
                    Layout.column: 0
                    text: modelData.name
                    enabled: modelData.installed
                    checked: page.cfg_agent === modelData.id
                    onToggled: if (checked) page.cfg_agent = modelData.id
                }
            }
            Repeater {
                model: page.agents
                delegate: QQC2.ComboBox {
                    required property var modelData
                    required property int index
                    readonly property string key: "cfg_" + modelData.id + "_model"
                    readonly property string defaultText: i18n("default model")
                    Layout.row: index
                    Layout.column: 1
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 9
                    visible: modelData.models
                    editable: true
                    model: modelData.id === "claude" ? [defaultText, "fable", "opus", "sonnet", "haiku"] : [defaultText]
                    Component.onCompleted: editText = (page[key] || "default") === "default" ? defaultText : page[key]
                    onEditTextChanged: {
                        const value = editText.trim()
                        page[key] = value === "" || value === defaultText ? "default" : value
                    }
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: i18n("Type a model name the agent accepts, or leave it on the default.")
                }
            }
            Repeater {
                model: page.agents
                delegate: Item {
                    required property var modelData
                    required property int index
                    Layout.row: index
                    Layout.column: 2
                    implicitWidth: install.visible ? install.implicitWidth : ok.implicitWidth
                    implicitHeight: install.implicitHeight

                    QQC2.Label {
                        id: ok
                        anchors.verticalCenter: parent.verticalCenter
                        visible: modelData.installed
                        text: i18n("installed")
                        opacity: 0.6
                    }
                    QQC2.Button {
                        id: install
                        visible: !modelData.installed
                        icon.name: "download"
                        text: i18n("Install")
                        onClicked: shell.run("setsid -f lili-crash install " + modelData.id + " >/dev/null 2>&1")
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.text: i18n("Runs the official installer in a terminal, in your home folder, without sudo.")
                    }
                }
            }
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Diagnosis skill")
        }

        QQC2.Label {
            Kirigami.FormData.label: i18n("Notes for:")
            text: page.distro.name ? (page.distro.edited ? i18n("%1 (edited by you)", page.distro.name) : page.distro.name) : ""
        }
        RowLayout {
            QQC2.Button {
                icon.name: "document-preview"
                text: i18n("View")
                onClicked: shell.run("lili-crash skill view")
            }
            QQC2.Button {
                icon.name: "document-edit"
                text: i18n("Edit")
                onClicked: shell.run("lili-crash skill edit")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.text: i18n("Your copy is kept in ~/.config/lili/skills, so updates never overwrite it.")
            }
            QQC2.Button {
                visible: !!page.distro.edited
                icon.name: "edit-reset"
                text: i18n("Restore default")
                onClicked: shell.run("lili-crash skill reset && lili-crash config")
            }
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Terminal")
        }

        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Open in:")
            textRole: "text"
            valueRole: "value"
            model: [{ value: "auto", text: i18n("Automatic") }].concat(
                page.installedTerminals.map(t => ({ value: t, text: t })))
            onModelChanged: currentIndex = Math.max(0, indexOfValue(page.cfg_terminal))
            onActivated: page.cfg_terminal = currentValue
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Shell afterwards:")
            model: ["fish", "bash", "zsh"]
            Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.cfg_shell))
            onActivated: page.cfg_shell = currentValue
        }

        QQC2.Label {
            Kirigami.FormData.isSection: true
            text: i18n("Lili speaks your system's language.")
            opacity: 0.6
        }
    }
}
