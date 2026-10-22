"""Exercise the actual Qt controls, including cancellation and the confirmed AI handoff."""
import gettext
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from test_packages import lili

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton
    spec = importlib.util.spec_from_file_location("package_window", lili.ROOT / "share/package_window.py")
    window = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(window)


@unittest.skipUnless(HAS_QT, "The Arch package window needs PySide6")
class PackageWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.translate = staticmethod(gettext.translation("lili", lili.ROOT / "locale", languages=["pt_BR"], fallback=True).gettext)

    def setUp(self):
        self.info = {"path": "/home/test/Downloads/aplicativo-1.2.3-amd64.deb", "format": "deb",
                     "size": 24576000, "sha256": "a" * 64}
        self.dialog = window.PackageWindow(self.info, "Garuda Linux", "Ollama (IA local)",
                                          lili.ROOT / "assets/logo/lili-crash.svg", self.translate)
        self.dialog.show()
        self.app.processEvents()
        self.addCleanup(self.dialog.close)

    def test_brand_details_and_responsive_footer(self):
        self.assertFalse(self.dialog.findChild(QLabel, "liliLogo").pixmap().isNull())
        details = self.dialog.findChild(QLabel, "fileDetails")
        self.assertFalse(details.isVisible())
        QTest.mouseClick(self.dialog.findChild(QPushButton, "detailsToggle"), Qt.MouseButton.LeftButton)
        self.assertTrue(details.isVisible())
        self.assertIn(self.info["path"], details.text())
        self.dialog.resize(480, 520)
        self.app.processEvents()
        for name in ("cancel", "install"):
            button = self.dialog.findChild(QPushButton, name)
            self.assertTrue(button.isVisible())
            origin = button.mapTo(self.dialog, button.rect().topLeft())
            self.assertTrue(self.dialog.rect().contains(origin))
            self.assertTrue(self.dialog.rect().contains(button.mapTo(self.dialog, button.rect().bottomRight())))

    def test_cancel_escape_and_enter_do_not_accept(self):
        for action in ("cancel", "escape", "enter"):
            with self.subTest(action=action):
                self.dialog.show()
                self.dialog.findChild(QPushButton, "cancel").setFocus()
                if action == "cancel":
                    QTest.mouseClick(self.dialog.findChild(QPushButton, "cancel"), Qt.MouseButton.LeftButton)
                else:
                    QTest.keyClick(self.dialog, Qt.Key.Key_Escape if action == "escape" else Qt.Key.Key_Return)
                self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
                self.assertFalse(self.dialog.isVisible())

    def test_install_click_accepts(self):
        QTest.mouseClick(self.dialog.findChild(QPushButton, "install"), Qt.MouseButton.LeftButton)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    def test_install_can_be_chosen_with_keyboard(self):
        button = self.dialog.findChild(QPushButton, "install")
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Return)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    def test_real_package_open_with_qt_buttons_and_captured_agent(self):
        self.dialog.close()
        for suffix in ("deb", "rpm"):
            real = next((lili.ROOT / "packages/0.5.1").rglob(f"*.{suffix}"), None)
            if real is None:
                continue
            for button in ("cancel", "install"):
                failures = []

                def click():
                    try:
                        target = QApplication.activeModalWidget()
                        self.assertIsNotNone(target)
                        QTest.mouseClick(target.findChild(QPushButton, button), Qt.MouseButton.LeftButton)
                    except Exception as error:
                        failures.append(error)
                        if QApplication.activeModalWidget():
                            QApplication.activeModalWidget().reject()

                with self.subTest(suffix=suffix, button=button), patch.object(lili, "arch_host", return_value=True), \
                        patch.object(lili, "which", return_value="agent"), patch.object(lili, "terminal_command"), \
                        patch.object(lili, "launch_agent") as agent:
                    QTimer.singleShot(50, click)
                    lili.package_open(str(real))
                    self.assertFalse(failures, failures)
                    if button == "install":
                        agent.assert_called_once()
                        self.assertTrue(agent.call_args.kwargs["installing"])
                        self.assertIn(lili.inspect_package(str(real))["sha256"], agent.call_args.args[1])
                    else:
                        agent.assert_not_called()

    def test_light_dark_and_small_window_render(self):
        output = os.environ.get("LILI_UI_SCREENSHOTS")
        for theme, color in (("light", "#ffffff"), ("dark", "#18161b")):
            palette = QPalette(self.app.palette())
            palette.setColor(QPalette.ColorRole.Window, QColor(color))
            with self.subTest(theme=theme):
                self.app.setPalette(palette)
                dialog = window.PackageWindow(self.info, "Garuda Linux", "Ollama (IA local)",
                                              lili.ROOT / "assets/logo/lili-crash.svg", self.translate)
                try:
                    dialog.show()
                    self.app.processEvents()
                    image = dialog.grab()
                    self.assertFalse(image.isNull())
                    if output:
                        folder = Path(output)
                        folder.mkdir(parents=True, exist_ok=True)
                        image.save(str(folder / f"lili-package-{theme}.png"))
                    dialog.resize(480, 520)
                    self.app.processEvents()
                    if output:
                        dialog.grab().save(str(folder / f"lili-package-{theme}-small.png"))
                finally:
                    dialog.close()
