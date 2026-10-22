"""Foreign package opening must require a click, and keep installation in the AI handoff."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("lili_packages", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)


def ar_member(name, data):
    header = f"{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n".encode()
    return header + data + (b"\n" if len(data) % 2 else b"")


class PackageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.package = self.root / "sample.deb"
        self.package.write_bytes(b"!<arch>\n" + ar_member("debian-binary", b"2.0\n") +
                                 ar_member("control.tar.gz", b"control") + ar_member("data.tar.gz", b"payload"))
        for name, value in {"STATE_DIR": self.root / "state", "CONFIG_FILE": self.root / "config.json"}.items():
            mock = patch.object(lili, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_deb_contents_and_digest_are_identified_without_extraction(self):
        info = lili.inspect_package(str(self.package))
        self.assertEqual(info["format"], "deb")
        self.assertEqual(info["path"], str(self.package))
        self.assertEqual(info["sha256"], lili.hashlib.sha256(self.package.read_bytes()).hexdigest())
        self.assertEqual(list(self.root.iterdir()), [self.package])

    def test_shipped_real_deb_and_rpm_packages_are_recognized(self):
        for suffix in ("deb", "rpm"):
            package = next((lili.ROOT / "packages" / "0.5.1").rglob(f"*.{suffix}"), None)
            if package:
                with self.subTest(suffix=suffix):
                    self.assertEqual(lili.inspect_package(str(package))["format"], suffix)

    def test_local_uri_and_special_filename(self):
        target = self.root / "spaces ' $() & <image> %.deb"
        self.package.rename(target)
        self.assertEqual(lili.inspect_package(target.as_uri())["path"], str(target))

    def test_remote_uri_rejected(self):
        for uri in ("file://remote/tmp/file.deb", "https://example.org/file.deb"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                lili.inspect_package(uri)

    def test_renamed_text_truncated_ar_and_missing_members_rejected(self):
        for data in (b"not a package", b"!<arch>\n", b"!<arch>\n" + ar_member("debian-binary", b"2.0\n"),
                     self.package.read_bytes()[:-2]):
            self.package.write_bytes(data)
            with self.assertRaises(ValueError):
                lili.inspect_package(str(self.package))

    def test_wrong_extension_rejected(self):
        wrong = self.package.with_suffix(".rpm")
        self.package.rename(wrong)
        with self.assertRaises(ValueError):
            lili.inspect_package(str(wrong))

    def test_fifo_rejected_without_reading(self):
        fifo = self.root / "pipe.deb"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            lili.inspect_package(str(fifo))

    def test_cancel_never_launches_agent(self):
        with patch.object(lili, "arch_host", return_value=True), patch.object(lili, "which", return_value="claude"), \
                patch.object(lili, "package_confirmation", return_value=False), patch.object(lili, "launch_agent") as launch:
            lili.package_open(str(self.package))
            launch.assert_not_called()

    def test_install_click_hands_verified_file_to_agent(self):
        with patch.object(lili, "arch_host", return_value=True), patch.object(lili, "which", return_value="claude"), \
                patch.object(lili, "package_confirmation", return_value=True), patch.object(lili, "terminal_command"), \
                patch.object(lili, "launch_agent") as launch:
            lili.package_open(str(self.package))
            launch.assert_called_once()
            self.assertTrue(launch.call_args.kwargs["installing"])
            self.assertIn(lili.inspect_package(str(self.package))["sha256"], launch.call_args.args[1])

    def test_replaced_file_after_click_does_not_launch(self):
        def answer(*args, **kwargs):
            self.package.write_bytes(b"replaced")
            return True
        with patch.object(lili, "arch_host", return_value=True), patch.object(lili, "which", return_value="claude"), \
                patch.object(lili, "package_confirmation", side_effect=answer), patch.object(lili, "package_dialog"), patch.object(lili, "launch_agent") as launch:
            with self.assertRaises(SystemExit):
                lili.package_open(str(self.package))
            launch.assert_not_called()

    def test_unsupported_host_and_missing_agent_show_error_without_install(self):
        for arch, binary in ((False, "claude"), (True, None)):
            with self.subTest(arch=arch), patch.object(lili, "arch_host", return_value=arch), \
                    patch.object(lili, "which", return_value=binary), patch.object(lili, "package_dialog") as dialog, \
                    patch.object(lili, "launch_agent") as launch:
                with self.assertRaises(SystemExit):
                    lili.package_open(str(self.package))
                self.assertFalse(dialog.call_args.kwargs.get("confirm"))
                launch.assert_not_called()

    def test_dialog_escapes_markup_and_launches_without_shell(self):
        with patch.object(lili.shutil, "which", return_value="kdialog"), patch.object(lili.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(lili.package_dialog('<img src="x"> & $(touch /tmp/no)', confirm=True))
            argv = run.call_args.args[0]
            self.assertIn("--yesno", argv)
            self.assertNotIn("<img", argv[-1])
            self.assertIn("&lt;img", argv[-1])
            self.assertFalse(run.call_args.kwargs.get("shell"))

    def test_zenity_cancel_and_missing_gui_do_not_approve(self):
        with patch.object(lili.shutil, "which", side_effect=lambda cmd: cmd if cmd == "zenity" else None), \
                patch.object(lili.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.assertFalse(lili.package_dialog("package", confirm=True))
            self.assertIn("--no-markup", run.call_args.args[0])
        with patch.object(lili.shutil, "which", return_value=None), self.assertRaises(RuntimeError):
            lili.package_dialog("package", confirm=True)

    def test_install_mode_does_not_relax_diagnosis_permissions(self):
        settings = lili.load_config()
        self.assertEqual(lili.opencode_config(settings)["permission"]["edit"], "deny")
        install = lili.opencode_config(settings, installing=True)["permission"]
        self.assertEqual(install["edit"], "ask")
        self.assertEqual(install["bash"]["*"], "ask")

    def test_arch_detection_includes_derivatives(self):
        for info, expected in (({"ID": "arch"}, True), ({"ID": "garuda", "ID_LIKE": "arch"}, True),
                               ({"ID": "manjaro", "ID_LIKE": "arch"}, True), ({"ID": "debian"}, False)):
            with self.subTest(info=info), patch.object(lili, "os_release", return_value=info):
                self.assertEqual(lili.arch_host(), expected)

    def test_setup_saves_old_defaults_registers_once_and_respects_later_changes(self):
        associations = {mime: "org.kde.ark.desktop" for mime in lili.PACKAGE_MIMES}

        def run(argv, **kwargs):
            if argv[:3] == ["xdg-mime", "query", "default"] and not (lili.STATE_DIR / "package-handlers.json").exists():
                self.assertFalse((self.root / "data/applications" / lili.PACKAGE_DESKTOP).exists())
            if argv[:2] == ["xdg-mime", "default"]:
                associations[argv[3]] = argv[2]
            result = associations.get(argv[-1], "") if argv[:3] == ["xdg-mime", "query", "default"] else ""
            return subprocess.CompletedProcess(argv, 0, result)

        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data")}), \
                patch.object(lili.importlib.util, "find_spec", return_value=True), \
                patch.object(lili, "arch_host", return_value=True), patch.object(lili.shutil, "which", return_value="tool"), \
                patch.object(lili.subprocess, "run", side_effect=run) as commands, patch.object(lili, "link_skill"):
            lili.setup_package_support()
            saved = json.loads((lili.STATE_DIR / "package-handlers.json").read_text())
            self.assertTrue(saved["installed"])
            self.assertEqual(set(saved["previous"].values()), {"org.kde.ark.desktop"})
            self.assertEqual(set(associations.values()), {lili.PACKAGE_DESKTOP})
            desktop = self.root / "data/applications" / lili.PACKAGE_DESKTOP
            self.assertIn("package-open %f", desktop.read_text())
            associations[lili.PACKAGE_MIMES[0]] = "another.desktop"
            commands.reset_mock()
            lili.setup_package_support()
            commands.assert_not_called()
            self.assertEqual(associations[lili.PACKAGE_MIMES[0]], "another.desktop")

    def test_setup_on_other_distros_does_not_change_associations(self):
        with patch.object(lili, "arch_host", return_value=False), patch.object(lili.subprocess, "run") as run:
            lili.setup_package_support()
            run.assert_not_called()
            self.assertFalse(lili.STATE_DIR.exists())

    def test_failed_registration_does_not_claim_success(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data")}), \
                patch.object(lili.importlib.util, "find_spec", return_value=True), \
                patch.object(lili, "arch_host", return_value=True), patch.object(lili.shutil, "which", return_value="tool"), \
                patch.object(lili.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ark.desktop")):
            with self.assertRaises(RuntimeError):
                lili.setup_package_support()
            saved = json.loads((lili.STATE_DIR / "package-handlers.json").read_text())
            self.assertFalse(saved.get("installed", False))


if __name__ == "__main__":
    unittest.main()
