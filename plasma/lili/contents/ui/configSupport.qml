import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    // The dialog hands every page every setting; this one only shows addresses.
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

    readonly property var wallets: [
        { name: "Bitcoin", address: "bc1q2nqp9d8lc0u6z7v9ag4u52sv9g9afepgyyrwu4", qr: "../images/donate-btc.png", networks: "" },
        // One address takes donations on every EVM network Vurto Swap supports.
        { name: i18n("EVM networks"), address: "0x930CD3e9de6F2dB03709667C9799d073b34FEaCc", qr: "../images/donate-evm.png",
          networks: "Ethereum · Optimism · BNB Chain · Gnosis · Polygon · Base · Arbitrum One · Avalanche · Unichain" },
    ]

    // QML has no clipboard API; a hidden text field can copy its own text.
    TextEdit {
        id: clipboard
        visible: false
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing * 2

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: i18n("Lili Crash is free and stays free. If she saved you an evening of digging through logs, a donation keeps her going.")
        }

        Repeater {
            model: page.wallets
            delegate: ColumnLayout {
                required property var modelData
                Layout.alignment: Qt.AlignHCenter
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Heading {
                    level: 3
                    text: modelData.name
                    Layout.alignment: Qt.AlignHCenter
                }
                QQC2.Label {
                    visible: modelData.networks !== ""
                    text: modelData.networks
                    opacity: 0.7
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.maximumWidth: Kirigami.Units.gridUnit * 24
                    Layout.alignment: Qt.AlignHCenter
                }
                Image {
                    source: Qt.resolvedUrl(modelData.qr)
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 10
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 10
                    Layout.alignment: Qt.AlignHCenter
                    fillMode: Image.PreserveAspectFit
                    smooth: false
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    QQC2.TextField {
                        text: modelData.address
                        readOnly: true
                        selectByMouse: true
                        font.family: "monospace"
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 22
                    }
                    QQC2.Button {
                        id: copy
                        icon.name: "edit-copy"
                        text: i18n("Copy")
                        onClicked: {
                            clipboard.text = modelData.address
                            clipboard.selectAll()
                            clipboard.copy()
                            copy.text = i18n("Copied")
                            restore.restart()
                        }
                        Timer {
                            id: restore
                            interval: 2000
                            onTriggered: copy.text = i18n("Copy")
                        }
                    }
                }
            }
        }
    }
}
