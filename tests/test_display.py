"""Recovery is opt-in, panel-specific, bounded and honest about visual confirmation."""
import copy
import gettext
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_packages import lili

display = lili.display
NOW = 1800000000
IDENTITY = {"edid": "a" * 64, "driver": "i915", "dpms": "On"}


def screens(hz=240):
    return [{"name": "HDMI-A-1", "enabled": True, "connected": True, "currentModeId": "1",
             "modes": [{"id": "1", "refreshRate": 75, "size": {"width": 1920, "height": 1080}}],
             "pos": {"x": 0, "y": 0}, "scale": 1},
            {"name": "eDP-2", "enabled": True, "connected": True,
             "currentModeId": "25" if hz == 240 else "26", "pos": {"x": 86, "y": 1080}, "scale": 1.2,
             "modes": [{"id": str(i), "refreshRate": r, "size": {"width": 2560, "height": 1600}}
                       for i, r in ((25, 240), (26, 60))]}]


class DisplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tracker = {}
        self.mocks = {}
        for name, value in (("outputs", screens()), ("panel_identity", IDENTITY),
                            ("session_ready", True), ("video_errors", 0), ("run", "")):
            mock = patch.object(display, name, return_value=copy.deepcopy(value))
            self.mocks[name] = mock.start()
            self.addCleanup(mock.stop)
        self.policy = {"enabled": True, "output": "eDP-2", **IDENTITY,
                       "size": {"width": 2560, "height": 1600}, "refresh": 60, "approved_at": NOW - 100}
        self.save({"policy": self.policy})

    def save(self, value):
        display.write_json(self.root / "display.json", value)

    def state(self):
        return json.loads((self.root / "display.json").read_text())

    def poll(self, now=NOW):
        return display.poll(self.root, self.tracker, now)

    def test_no_approval_never_queries_or_repairs(self):
        self.save({})
        self.assertIsNone(self.poll())
        self.mocks["outputs"].assert_not_called()
        self.mocks["run"].assert_not_called()

    def test_session_return_restores_only_panel_and_records_verification(self):
        self.mocks["outputs"].side_effect = [screens(), screens(60)]
        item = self.poll()
        self.assertEqual(item["status"], "applied")
        self.assertEqual(item["trigger"], "session-return")
        self.mocks["run"].assert_called_once_with(["kscreen-doctor", "output.eDP-2.mode.26"])
        self.assertEqual(self.state()["events"][0]["after_hz"], 60)
        self.assertEqual((self.root / "display.json").stat().st_mode & 0o777, 0o600)
        self.assertIn("visual confirmation", display.report_text(item, lambda s: s))

    def test_locked_lid_closed_or_unknown_session_never_repairs(self):
        self.mocks["session_ready"].return_value = False
        self.assertIsNone(self.poll())
        self.mocks["outputs"].assert_not_called()
        self.mocks["session_ready"].return_value = True
        self.mocks["outputs"].side_effect = [screens(), screens(60)]
        self.assertEqual(self.poll(NOW + 10)["status"], "applied")

    def test_dpms_off_then_on_is_a_session_return(self):
        self.tracker.update(ready=True, time=NOW - 10)
        self.mocks["panel_identity"].return_value = {**IDENTITY, "dpms": "Off"}
        self.assertIsNone(self.poll())
        self.mocks["panel_identity"].return_value = IDENTITY
        self.mocks["outputs"].side_effect = [screens(), screens(60)]
        self.assertEqual(self.poll(NOW + 10)["status"], "applied")

    def test_wrong_panel_driver_disconnected_disabled_or_resolution_are_untouched(self):
        for change in ("edid", "driver", "enabled", "connected", "size", "missing-mode"):
            with self.subTest(change=change):
                self.tracker.clear()
                self.mocks["panel_identity"].return_value = dict(IDENTITY)
                value = screens()
                if change in ("edid", "driver"):
                    self.mocks["panel_identity"].return_value[change] = "different"
                elif change in ("enabled", "connected"):
                    value[1][change] = False
                elif change == "size":
                    value[1]["modes"][0]["size"]["width"] = 1920
                else:
                    value[1]["modes"].pop()
                self.mocks["outputs"].return_value = value
                self.assertIsNone(self.poll())
        self.mocks["run"].assert_not_called()

    def test_already_stable_mode_has_no_repair_or_success_notice(self):
        self.mocks["outputs"].return_value = screens(60)
        self.assertIsNone(self.poll())
        self.mocks["video_errors"].return_value = NOW + 5
        item = self.poll(NOW + 10)
        self.assertEqual(item["status"], "needs-attention")
        self.mocks["run"].assert_not_called()

    def test_failure_and_timeout_are_recorded_and_cooldown_survives_restart(self):
        for error in (RuntimeError("failed"), subprocess.TimeoutExpired("kscreen-doctor", 10)):
            with self.subTest(error=error):
                self.save({"policy": self.policy})
                self.tracker.clear()
                self.mocks["run"].side_effect = error
                item = self.poll()
                self.assertEqual(item["status"], "failed")
                self.tracker.clear()
                self.assertIsNone(self.poll(NOW + 10))
                self.assertEqual(len(self.state()["events"]), 1)

    def test_external_change_or_unchanged_mode_is_not_success(self):
        for after in (screens(), screens(60)):
            self.save({"policy": self.policy})
            self.tracker.clear()
            if after[1]["currentModeId"] == "26":
                after[0]["enabled"] = False
            self.mocks["outputs"].side_effect = [screens(), after]
            self.assertEqual(self.poll()["status"], "failed")

    def test_fresh_errors_recover_without_unlock_and_are_not_replayed(self):
        self.tracker.update(ready=True, time=NOW - 10)
        self.mocks["video_errors"].side_effect = [NOW - 1, 0]
        self.mocks["outputs"].side_effect = [screens(), screens(60)]
        self.assertEqual(self.poll()["trigger"], "video-errors")
        self.assertEqual(self.state()["errors_until"], NOW - 1)
        self.tracker["time"] = NOW + 390
        self.assertIsNone(self.poll(NOW + 400))
        self.mocks["run"].assert_called_once()

    def rewake_setup(self, after=None):
        """A 60 Hz panel and a kscreen-doctor whose DPMS really moves the connector's state."""
        dpms = self.root / "dpms"
        dpms.write_text("On\n")
        self.mocks["panel_identity"].return_value = {**IDENTITY, "connector": str(self.root)}
        self.mocks["outputs"].side_effect = [screens(60), screens(60), after or screens(60)]

        def run(argv):
            if argv[1:] == ["--dpms", "off"]:
                dpms.write_text("Off\n")
            elif argv[1:] == ["--dpms", "on"]:
                dpms.write_text("On\n")
            return ""
        self.mocks["run"].side_effect = run
        mock = patch.object(display, "OFF_SECONDS", 0)
        mock.start()
        self.addCleanup(mock.stop)
        return dpms

    def test_a_stable_panel_is_rewoken_only_after_the_screens_were_off(self):
        self.rewake_setup()
        self.tracker.update(ready=True, time=NOW - 10, slept=True)
        item = self.poll()
        self.assertEqual((item["trigger"], item["status"]), ("display-wake", "rewoken"))
        self.assertEqual([c.args[0][1:] for c in self.mocks["run"].call_args_list],
                         [["--dpms", "off"], ["--dpms", "on"]])
        # Its own power cycle is not a new wake, and neither is the next quiet poll.
        self.mocks["run"].reset_mock()
        self.assertIsNone(self.poll(NOW + 400 - 360))
        self.assertIsNone(self.poll(NOW + 400 - 320))
        self.mocks["run"].assert_not_called()

    def test_wake_while_locked_waits_for_the_unlock(self):
        self.rewake_setup()
        self.tracker.update(ready=True, time=NOW - 10, slept=True)
        self.mocks["session_ready"].return_value = False
        self.assertIsNone(self.poll())
        self.mocks["run"].assert_not_called()
        self.mocks["session_ready"].return_value = True
        self.assertEqual(self.poll(NOW + 2)["status"], "rewoken")

    def test_a_plain_unlock_with_screens_on_does_not_blink(self):
        self.rewake_setup()
        self.tracker.update(ready=False, time=NOW - 2)
        self.assertIsNone(self.poll())
        self.mocks["run"].assert_not_called()

    def test_screens_are_turned_back_on_when_off_fails_and_layout_changes_are_not_success(self):
        changed = screens(60)
        changed[0]["enabled"] = False
        for after, error in ((None, RuntimeError("off failed")), (changed, None)):
            with self.subTest(error=error):
                self.save({"policy": self.policy})
                self.rewake_setup(after)
                if error:
                    self.mocks["run"].side_effect = [error, ""]
                self.tracker.clear()
                self.tracker.update(ready=True, time=NOW - 10, slept=True)
                self.assertEqual(self.poll()["status"], "failed")
                self.assertEqual(self.mocks["run"].call_args.args[0][1:], ["--dpms", "on"])

    def test_panel_renumbered_by_the_kernel_is_still_the_approved_one(self):
        self.rewake_setup()
        renamed = [[{**o, "name": o["name"].replace("eDP-2", "eDP-1")} for o in screens(60)] for _ in range(3)]
        self.mocks["outputs"].side_effect = renamed
        identity = self.mocks["panel_identity"].return_value
        self.mocks["panel_identity"].side_effect = lambda name, drm=None: identity if name == "eDP-1" else None
        with patch.object(display.Path, "glob", return_value=[Path("card0-eDP-2"), Path("card1-eDP-1")]):
            self.tracker.update(ready=True, time=NOW - 10, slept=True)
            self.assertEqual(self.poll()["output"], "eDP-1")
        self.assertEqual(self.state()["policy"]["output"], "eDP-1")

    def test_manual_rewake_ignores_cooldown_but_needs_approval(self):
        self.rewake_setup()
        self.save({"policy": self.policy, "last_attempt": display.time.time()})
        self.mocks["outputs"].side_effect = [screens(60)] * 3
        self.assertEqual(display.rewake_now(self.root)["status"], "rewoken")
        self.save({"policy": {**self.policy, "enabled": False}})
        with self.assertRaises(ValueError):
            display.rewake_now(self.root)

    def test_a_short_screen_off_between_polls_is_noticed(self):
        (self.root / "dpms").write_text("Off\n")
        tracker = {"ready": False, "dpms": str(self.root / "dpms")}
        with patch.object(display.time, "sleep"):
            display.wait(tracker)
        self.assertTrue(tracker["slept"])

    def test_approval_requires_current_stable_panel_and_records_user_confirmation(self):
        with self.assertRaises(ValueError):
            display.approve(self.root, "eDP-2", 240)
        self.mocks["outputs"].return_value = screens(60)
        item = display.approve(self.root, "eDP-2", 240)
        self.assertEqual(item["status"], "confirmed")
        self.assertTrue(self.state()["policy"]["enabled"])
        self.mocks["run"].assert_not_called()


class EvidenceTests(unittest.TestCase):
    def test_poll_commands_use_utf8_without_changing_the_session_environment(self):
        with patch.dict(os.environ, {"LC_ALL": "pt_BR.UTF-8"}), \
                patch.object(display.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "false\n"
            self.assertEqual(display.run(["qdbus6", "test"]), "false\n")
            self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C.UTF-8")
            self.assertEqual(os.environ["LC_ALL"], "pt_BR.UTF-8")

    def test_requires_fresh_distinct_busy_events_but_one_explicit_timeout(self):
        def line(t, msg):
            return json.dumps({"__REALTIME_TIMESTAMP": str(t * 1000000), "MESSAGE": msg})
        for entries, expected in (([(NOW - 1, "Atomic commit failed: EBUSY")] * 3, 0),
                                  ([(NOW - i, "Atomic commit failed: EBUSY") for i in (1, 2, 3)], NOW - 1),
                                  ([(NOW - 1, "i915: flip_done timed out")], NOW - 1),
                                  ([(NOW - 700, "i915: flip_done timed out")], 0),
                                  ([(NOW + 10, "i915: flip_done timed out")], 0)):
            with self.subTest(entries=entries), patch.object(display, "run", side_effect=[
                    "\n".join(line(*entry) for entry in entries), RuntimeError("kernel denied")]):
                self.assertEqual(display.video_errors(NOW - 600, NOW), expected)

    def test_unknown_or_closed_lid_and_locked_session_fail_closed(self):
        with tempfile.TemporaryDirectory() as root, patch.object(display, "run", return_value="false\n") as run:
            lid = Path(root)
            self.assertFalse(display.session_ready(lid))
            (lid / "LID0").mkdir()
            (lid / "LID0/state").write_text("state: open\n")
            self.assertTrue(display.session_ready(lid))
            run.return_value = "true\n"
            self.assertFalse(display.session_ready(lid))
            run.return_value = "false\n"
            (lid / "LID0/state").write_text("state: closed\n")
            self.assertFalse(display.session_ready(lid))

    def test_real_sysfs_card_and_connector_link_shape(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            card = root / "card0"
            connector = root / "card0-eDP-2"
            pci = root / "pci"
            driver = root / "i915"
            for path in (card, connector, pci, driver):
                path.mkdir()
            (connector / "device").symlink_to(card)
            (card / "device").symlink_to(pci)
            (pci / "driver").symlink_to(driver)
            (connector / "edid").write_bytes(b"a" * 128)
            (connector / "status").write_text("connected\n")
            (connector / "dpms").write_text("On\n")
            self.assertEqual(display.panel_identity("eDP-2", root)["driver"], "i915")
            self.assertIsNone(display.panel_identity("HDMI-A-1", root))


class DisplayWindowTests(unittest.TestCase):
    def test_report_stays_open_until_closed_and_uses_portuguese(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QTextBrowser
        except ImportError:
            self.skipTest("Qt not installed")
        app = QApplication.instance() or QApplication([])
        translate = gettext.translation("lili", lili.ROOT / "locale", languages=["pt_BR"], fallback=True).gettext
        item = {"output": "eDP-2", "before_hz": 240, "after_hz": 60,
                "trigger": "user-confirmed", "status": "confirmed"}
        dialog = display.create_dialog(item, translate, lili.ROOT / "assets/logo/lili-crash.svg")
        dialog.show()
        app.processEvents()
        self.assertTrue(dialog.isVisible())
        text = dialog.findChild(QTextBrowser).toPlainText()
        self.assertIn("240 → 60 Hz", text)
        self.assertIn("confirmada pelo usuário", text)
        dialog.close()
        self.assertFalse(dialog.isVisible())

    def test_the_button_asks_for_another_wake(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QDialogButtonBox
        except ImportError:
            self.skipTest("Qt not installed")
        app = QApplication.instance() or QApplication([])
        asked = []
        item = {"output": "eDP-1", "before_hz": 60, "after_hz": 60,
                "trigger": "display-wake", "status": "rewoken"}
        dialog = display.create_dialog(item, lambda s: s, lili.ROOT / "assets/logo/lili-crash.svg",
                                       lambda: asked.append(True))
        box = dialog.findChild(QDialogButtonBox)
        next(b for b in box.buttons() if box.buttonRole(b) == QDialogButtonBox.ButtonRole.ActionRole).click()
        self.assertEqual(asked, [True])
