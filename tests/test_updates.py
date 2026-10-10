"""Updater errors must work without a core dump, root, or a desktop service exit."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("lili", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)

HEADER = ">-<->-< garuda-update at 2026-10-10 01:18 -03(-03)\n"
LOCK = "error: failed to synchronize all databases (unable to lock database)\n"


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "garuda-update"
        self.state = self.root / "state"
        for name, value in {"UPDATE_LOG": self.log, "STATE_DIR": self.state,
                            "STATE_FILE": self.state / "state.json", "UPDATES_FILE": self.state / "updates.json"}.items():
            mock = patch.object(lili, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.spawn = patch.object(lili.subprocess, "Popen").start()
        self.addCleanup(patch.stopall)

    def write(self, text=LOCK, header=HEADER):
        self.log.write_text(header + text)
        return next(iter(lili.scan_update_logs().values()), None)

    def test_actual_terminal_output_is_one_lock_event(self):
        run = self.write(":: Synchronizing package databases...\n" + LOCK +
                         "spawn pacman -Su -yy\r\n\x1b[?25l" + LOCK + "\x1b[?25h")
        self.assertEqual(run["kind"], "lock")
        self.assertEqual(run["lines"], [LOCK.strip()])
        self.assertTrue(lili.is_update(run["id"]))

    def test_portuguese_error(self):
        run = self.write("erro: falha ao sincronizar todas as bases de dados (não foi possível bloquear a base de dados)\n")
        self.assertEqual(run["kind"], "lock")

    def test_other_update_errors(self):
        run = self.write("error: failed retrieving file 'core.db' from mirror: Could not resolve host\n")
        self.assertEqual(run["kind"], "error")

    def test_healthy_missing_and_non_updater_logs_are_not_failures(self):
        self.assertEqual(lili.failed_updates(), [])
        self.write("warning: package is up to date\n:: Processing package changes...\n")
        self.assertEqual(lili.failed_updates(), [])
        self.write("Example: " + LOCK)
        self.assertEqual(lili.failed_updates(), [])
        self.write(LOCK, header="unrelated application\n")
        self.assertEqual(lili.failed_updates(), [])

    def test_unreadable_log_does_not_break_listing(self):
        with patch.object(Path, "open", side_effect=PermissionError):
            self.assertEqual(lili.failed_updates(), [])

    def test_large_log_reads_errors_near_end(self):
        self.assertEqual(self.write("package list\n" * 20000 + LOCK)["kind"], "lock")

    def test_repeat_output_rotation_and_restart_do_not_notify_again(self):
        run = self.write()
        lili.poll_updates()
        self.spawn.assert_called_once()
        with self.log.open("a") as stream:
            stream.write(LOCK)
        self.assertEqual(self.write(LOCK + LOCK)["id"], run["id"])
        self.log.rename(self.log.with_name("garuda-update.1"))
        lili.poll_updates()
        lili.poll_updates()  # A restarted watcher has no in-memory cursor.
        self.spawn.assert_called_once()
        self.assertEqual(len(lili.failed_updates()), 1)
        self.assertTrue(lili.find_update(run["id"])["log"].endswith(".1"))

    def test_new_run_notifies_after_rotation(self):
        first = self.write()
        lili.poll_updates()
        self.log.rename(self.log.with_name("garuda-update.1"))
        second = self.write(header=HEADER.replace("01:18", "01:19"))
        lili.poll_updates()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.spawn.call_count, 2)

    def test_evidence_survives_log_deletion(self):
        run = self.write()
        lili.poll_updates()
        self.log.unlink()
        self.assertEqual(lili.find_update(run["id"])["lines"], [LOCK.strip()])

    def test_old_errors_are_history_without_startup_notification(self):
        self.write()
        old = time.time() - 2 * 86400
        os.utime(self.log, (old, old))
        lili.poll_updates()
        self.spawn.assert_not_called()
        self.assertEqual(len(lili.failed_updates()), 1)

    def test_ignored_and_resolved_errors_do_not_notify(self):
        for state in ("ignored", "resolved", "diagnosed"):
            with self.subTest(state=state):
                self.write(header=HEADER.replace("01:18", state))
                lili.mark(lili.UPDATE_KEY, state)
                lili.poll_updates()
        self.spawn.assert_not_called()

    def test_new_error_after_resolution_becomes_new_in_history(self):
        self.write()
        lili.mark(lili.UPDATE_KEY, "resolved", "Previous attempt was fixed")
        lili.poll_updates()
        self.log.rename(self.log.with_name("garuda-update.1"))
        self.write(header=HEADER.replace("01:18", "01:20"))
        future = time.time() + 2
        os.utime(self.log, (future, future))
        with patch.object(lili, "crashes", return_value=[]), patch.object(lili, "freezes", return_value=[]), \
             patch.object(lili, "early_exits", return_value=[]), patch.object(lili, "steam_root", return_value=None), \
             patch.object(lili, "failed_launches", return_value=[]):
            program, = lili.programs()
        self.assertEqual(program["state"], "new")
        self.assertEqual(program["fresh"], 1)
        self.assertEqual(program["count"], 2)
        self.assertEqual(program["exe"], "update:garuda")
        self.assertTrue(lili.is_update(program["last"]["id"]))

    def test_notify_uses_update_title_and_diagnosis_action(self):
        run = self.write()
        with patch.object(lili.subprocess, "run") as command, patch.object(lili, "diagnose") as diagnose:
            command.return_value.stdout = "diagnose\n"
            lili.main(["notify", run["id"]])
        args = command.call_args.args[0]
        self.assertIn(lili._("System update reported an error"), args)
        self.assertIn(lili._("The package database is locked"), args[-1])
        diagnose.assert_called_once_with([run["id"]])

    def test_diagnose_passes_saved_evidence_and_lock_precautions(self):
        run = self.write()
        with patch.object(lili, "load_config", return_value={"agent": "claude"}), \
             patch.object(lili, "which", return_value="/usr/bin/claude"), \
             patch.object(lili, "virtualization", return_value=""), patch.object(lili, "open_terminal"):
            lili.main(["diagnose", run["id"]])
        prompt = next(self.state.glob("prompt-*")).read_text()
        self.assertIn("A system update reported an error", prompt)
        self.assertIn(LOCK.strip(), prompt)
        self.assertIn("Never delete the lock while a package manager is running", prompt)
        self.assertIn("key 'update:garuda'", prompt)

    def test_history_is_bounded_and_corrupt_json_recovers(self):
        self.state.mkdir()
        lili.UPDATES_FILE.write_text("bad json")
        self.write()
        lili.poll_updates()
        data = lili.read_update_history()
        run = next(iter(data["runs"].values()))
        data["runs"] = {str(n): {**run, "id": str(n), "time": n} for n in range(150)}
        lili.UPDATES_FILE.write_text(json.dumps(data))
        lili.poll_updates()
        self.assertEqual(len(lili.read_update_history()["runs"]), 100)
        self.assertEqual(len(lili.read_update_history()["notified"]), 100)


if __name__ == "__main__":
    unittest.main()
