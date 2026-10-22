"""Native, branded confirmation window. Import Qt only when a package is opened."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)


class PackageWindow(QDialog):
    def __init__(self, package, system, agent, logo, translate):
        super().__init__()
        _ = translate
        self.setWindowTitle(_("Lili Crash — Install an application"))
        self.setWindowIcon(QIcon(str(logo)))
        self.setObjectName("packageWindow")
        self.setMinimumWidth(460)
        dark = self.palette().window().color().lightness() < 128
        colors = (dict(bg="#18161b", card="#242127", ink="#f6f0f5", muted="#c2b7c2", line="#403741",
                       accent="#ffa3cc", button="#ee86b7", buttonink="#291021", hover="#ffa3cc", soft="#352532")
                  if dark else
                  dict(bg="#fcf9fb", card="#ffffff", ink="#291f2a", muted="#695c6b", line="#e1d6df",
                       accent="#a12462", button="#a12462", buttonink="#ffffff", hover="#851b50", soft="#f5e7ef"))
        self.setStyleSheet("""
            QDialog#packageWindow, QWidget#body, QScrollArea { background: %(bg)s; color: %(ink)s; }
            QLabel { color: %(ink)s; background: transparent; }
            QLabel[muted="true"] { color: %(muted)s; }
            QLabel[accent="true"] { color: %(accent)s; }
            QFrame#packageCard { background: %(card)s; border: 1px solid %(line)s; border-radius: 14px; }
            QFrame#footer { border-top: 1px solid %(line)s; background: %(bg)s; }
            QLabel#stepNumber { color: %(accent)s; background: %(soft)s; border-radius: 16px; }
            QPushButton { color: %(ink)s; background: transparent; border: 1px solid %(line)s;
                          border-radius: 9px; padding: 11px 18px; font-weight: 600; }
            QPushButton:hover { background: %(soft)s; }
            QPushButton:focus { border: 2px solid %(accent)s; }
            QPushButton#install { background: %(button)s; color: %(buttonink)s; border: 2px solid transparent; }
            QPushButton#install:hover { background: %(hover)s; }
            QPushButton#install:focus { border: 2px solid %(ink)s; }
            QPushButton#detailsToggle { border: none; color: %(accent)s; text-align: left; padding: 4px 0; }
            QPushButton#detailsToggle:focus { border: 1px solid %(accent)s; }
            QScrollArea { border: none; }
        """ % colors)

        def label(text, *, size=None, bold=False, muted=False, accent=False):
            item = QLabel(text)
            item.setTextFormat(Qt.TextFormat.PlainText)
            item.setWordWrap(True)
            item.setProperty("muted", muted)
            item.setProperty("accent", accent)
            font = QFont(self.font())
            if size:
                font.setPointSizeF(size)
            font.setBold(bold)
            item.setFont(font)
            return item

        base = max(10, self.font().pointSizeF())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("body")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(30, 26, 30, 22)
        layout.setSpacing(18)

        brand = QHBoxLayout()
        logo_label = QLabel()
        logo_label.setObjectName("liliLogo")
        logo_label.setPixmap(QIcon(str(logo)).pixmap(48, 48))
        logo_label.setAccessibleName(_("Lili flower logo"))
        logo_label.setFixedSize(52, 52)
        brand.addWidget(logo_label)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        brand_text.addWidget(label("Lili Crash", size=base + 3, bold=True))
        brand_text.addWidget(label(_("Application installation"), size=base - 1, muted=True))
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)

        heading = QVBoxLayout()
        heading.setSpacing(7)
        heading.addWidget(label(_("A package from another Linux."), size=base + 10, bold=True))
        heading.addWidget(label(_("Lili can help you install it on {system}.").format(system=system), muted=True))
        layout.addLayout(heading)

        card = QFrame()
        card.setObjectName("packageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 14)
        card_layout.setSpacing(12)
        filename = Path(package["path"]).name
        file_label = label(filename, bold=True)
        file_label.setObjectName("packageName")
        file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_label.setToolTip(package["path"])
        card_layout.addWidget(file_label)

        route = QHBoxLayout()
        origin = QVBoxLayout()
        origin.setSpacing(3)
        origin.addWidget(label(_("DETECTED FORMAT"), size=base - 2, muted=True))
        origin.addWidget(label("Debian · .deb" if package["format"] == "deb" else "RPM · .rpm", bold=True))
        route.addLayout(origin, 1)
        route.addWidget(label("→", size=base + 7, accent=True))
        route.addSpacing(14)
        host = QVBoxLayout()
        host.setSpacing(3)
        host.addWidget(label(_("YOUR SYSTEM"), size=base - 2, muted=True))
        host.addWidget(label(system, bold=True))
        route.addLayout(host, 1)
        card_layout.addLayout(route)

        details = label(_("File: {path}\nSize: {size}\nSHA-256: {digest}").format(
            path=package["path"], size=_size(package["size"]), digest=package["sha256"]), size=base - 1, muted=True)
        details.setObjectName("fileDetails")
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.hide()
        toggle = QPushButton(_("Show file details"))
        toggle.setObjectName("detailsToggle")
        toggle.setCheckable(True)
        toggle.setAutoDefault(False)
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(lambda checked: toggle.setText(_("Hide file details") if checked else _("Show file details")))
        card_layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        card_layout.addWidget(details)
        layout.addWidget(card)

        steps = QVBoxLayout()
        steps.setSpacing(14)
        steps.addWidget(label(_("WHAT HAPPENS NEXT"), size=base - 2, bold=True, muted=True))
        for number, title, description in (
            ("1", _("Check compatibility"), _("Check the application and the libraries it needs.")),
            ("2", _("Install for your system"), _("Use a native package, tracked by pacman.")),
            ("3", _("Make it ready to use"), _("Set up icons and the application-menu shortcut.")),
        ):
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = label(number, size=base, bold=True)
            badge.setObjectName("stepNumber")
            badge.setFixedSize(32, 32)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
            copy = QVBoxLayout()
            copy.setSpacing(3)
            copy.addWidget(label(title, bold=True))
            copy.addWidget(label(description, size=base - 1, muted=True))
            row.addLayout(copy, 1)
            steps.addLayout(row)
        layout.addLayout(steps)
        layout.addWidget(label(_("Assistant: {agent}").format(agent=agent), size=base - 1, bold=True))
        layout.addWidget(label(_("Your assistant opens in a terminal to check and install the app. "
                                 "If it cannot run here, it will explain why. Administrator authentication may be required."),
                               size=base - 1, muted=True))
        layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        actions = QVBoxLayout(footer)
        actions.setContentsMargins(30, 16, 30, 22)
        actions.setSpacing(12)
        actions.addWidget(label(_("Nothing is installed before you confirm."), size=base - 1, muted=True))
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        cancel = QPushButton(_("Cancel"))
        cancel.setObjectName("cancel")
        cancel.setMinimumHeight(44)
        cancel.clicked.connect(self.reject)
        cancel.setDefault(True)
        install = QPushButton(_("Install on this system"))
        install.setObjectName("install")
        install.setMinimumHeight(44)
        install.setAutoDefault(True)
        install.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(install)
        actions.addLayout(buttons)
        root.addWidget(footer)
        self.setTabOrder(toggle, cancel)
        self.setTabOrder(cancel, install)
        cancel.setFocus()
        self.resize(640, min(800, self.screen().availableGeometry().height() - 80))


def _size(value):
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def confirm_package(package, system, agent, logo, translate):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Lili Crash")
    app.setDesktopFileName("lili-crash")
    dialog = PackageWindow(package, system, agent, logo, translate)
    return dialog.exec() == QDialog.DialogCode.Accepted
