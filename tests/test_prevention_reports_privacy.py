"""Lifecycle, data minimization, fleet deduplication and remote-consent regressions."""
import copy
import importlib.machinery
import importlib.util
import json
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("lili_prevention", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)
health, reports, privacy = lili.health, lili.reports, lili.privacy
NOW = 1800000000
GIB = 1024**3


def sample(t=NOW, free=50 * GIB, memory=None, kernel=None, unavailable=None):
    result = {"time": t, "disks": {"root": {"free": free, "total": 100 * GIB,
               "inodes_free": 50000, "inodes_total": 100000, "device": 1}},
              "kernel": kernel or {}, "unavailable": unavailable or []}
    if memory is not None:
        result["memory"] = memory
    return result


class PreventionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def confirm(self, **kwargs):
        opened = []
        for i in range(3):
            opened += health.poll(self.root, sample(NOW + i * 60, **kwargs))
        return opened

    def test_transient_low_space_does_not_notify(self):
        self.assertEqual(health.poll(self.root, sample(free=GIB)), [])
        for i in range(1, 5):
            self.assertEqual(health.poll(self.root, sample(NOW + i * 60)), [])
        self.assertEqual(health.history(self.root), [])

    def test_btrfs_subvolumes_share_one_warning(self):
        mounts = "1 0 0:35 /@ / rw - btrfs /dev/disk-a rw\n2 1 0:52 /@home /home rw - btrfs /dev/disk-a rw\n3 1 8:2 / /var rw - ext4 /dev/disk-b rw"
        root = health.disk_identity(Path("/"), 35, mounts)
        self.assertEqual(root, health.disk_identity(Path("/home/alice"), 52, mounts))
        self.assertNotEqual(root, health.disk_identity(Path("/var"), 99, mounts))

    def test_episode_persists_once_across_restart_then_recovers_and_reopens(self):
        first = self.confirm(free=GIB)
        self.assertEqual(len(first), 1)
        for i in range(3, 7):
            self.assertEqual(health.poll(self.root, sample(NOW + i * 60, free=GIB)), [])
        for i in range(7, 10):
            health.poll(self.root, sample(NOW + i * 60))
        self.assertTrue(health.history(self.root)[0]["ended"])
        for i in range(10, 13):
            opened = health.poll(self.root, sample(NOW + i * 60, free=GIB))
        self.assertEqual(len(opened), 1)
        self.assertNotEqual(first[0]["id"], opened[0]["id"])

    def test_frequent_manual_polls_cannot_fake_persistence(self):
        for i in range(40):
            self.assertEqual(health.poll(self.root, sample(NOW + i, free=GIB)), [])

    def test_sleep_gap_cannot_confirm_a_warning(self):
        health.poll(self.root, sample(free=GIB))
        health.poll(self.root, sample(NOW + 60, free=GIB))
        self.assertEqual(health.poll(self.root, sample(NOW + 3600, free=GIB)), [])

    def test_active_warning_recovers_after_restart_gap(self):
        self.confirm(free=GIB)
        for i in range(3):
            health.poll(self.root, sample(NOW + 3600 + i * 60))
        self.assertTrue(health.history(self.root)[0]["ended"])

    def test_memory_needs_low_availability_and_sustained_stalls(self):
        self.assertEqual(self.confirm(memory={"available_pct": 5, "stall_pct": 0}), [])
        for i in range(3, 6):
            opened = health.poll(self.root, sample(NOW + i * 60, memory={"available_pct": 5, "stall_pct": 15}))
        self.assertEqual(opened[0]["code"], "memory-pressure")

    def test_unavailable_measurement_is_not_recovery(self):
        self.confirm(memory={"available_pct": 5, "stall_pct": 15})
        for i in range(3, 8):
            health.poll(self.root, sample(NOW + i * 60, unavailable=["memory-pressure"]))
        self.assertNotIn("ended", health.history(self.root)[0])

    def test_kernel_repeated_sampling_is_not_repeated_errors(self):
        self.assertEqual(self.confirm(kernel={"kernel-gpu": [NOW] * 20}), [])
        for i in range(3, 6):
            opened = health.poll(self.root, sample(NOW + i * 60, kernel={"kernel-gpu": [NOW, NOW + 1, NOW + 2]}))
        self.assertEqual(opened[0]["code"], "kernel-gpu")

    def test_disk_growth_requires_history_and_consistent_consumption(self):
        points = [sample(NOW + i * 60, free=(50 - i) * GIB) for i in range(16)]
        self.assertNotIn("disk-trend:root", health.candidates(points[4], points[:5]))
        trend = health.candidates(points[-1], points)["disk-trend:root"]
        self.assertAlmostEqual(trend["evidence"]["estimated_hours"], 35 / 60, places=2)
        # A single download at the end is not a sustained growth trend.
        for point in points[:-1]:
            point["disks"]["root"]["free"] = 50 * GIB
        self.assertNotIn("disk-trend:root", health.candidates(points[-1], points))

    def test_low_inodes_are_detected_even_with_free_disk_space(self):
        point = sample()
        point["disks"]["root"]["inodes_free"] = 10
        self.assertIn("disk-inodes:root", health.candidates(point, [point]))

    def test_ignored_and_recovered_warnings_integrate_with_history(self):
        event = self.confirm(free=GIB)[0]
        key = "health:" + event["key"]
        with patch.object(lili, "STATE_DIR", self.root):
            item = lili.health_programs({key: {"state": "ignored"}})[0]
            self.assertEqual(item["state"], "ignored")
            self.assertTrue(lili.is_health(item["last"]["id"]))
            for i in range(3, 6):
                health.poll(self.root, sample(NOW + i * 60))
            self.assertEqual(lili.health_programs({})[0]["state"], "resolved")

    def test_private_storage_and_no_raw_kernel_messages(self):
        self.confirm(kernel={"kernel-gpu": [NOW, NOW + 1, NOW + 2]})
        self.assertEqual((self.root / "health.json").stat().st_mode & 0o777, 0o600)
        event = health.history(self.root)[0]
        self.assertEqual(set(event["evidence"]), {"distinct_seconds", "window_seconds", "first_seen", "last_seen"})


class ReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.programs = [{"exe": "/usr/bin/example", "state": "new", "summary": "password=SECRETDATA",
                          "crashes": [{"pid": 100, "time": NOW - 10, "signal": "SIGSEGV", "lines": "token=SECRET"}]}]

    def report(self, folder="a"):
        return reports.build(self.programs, self.root / folder, now=NOW)

    def test_export_uses_allowlist_and_stable_private_machine_id(self):
        report = self.report()
        reports.validate(report)
        text = json.dumps(report)
        for secret in ("SECRETDATA", "token=SECRET", "/usr/bin", "summary", "pid"):
            self.assertNotIn(secret, text)
        self.assertEqual(report["events"][0]["component"], "example")
        self.assertEqual(report["machine_id"], self.report()["machine_id"])
        self.assertNotEqual(report["machine_id"], self.report("b")["machine_id"])

    def test_overlapping_exports_do_not_double_count_and_two_machines_correlate(self):
        a, b = self.report(), self.report("b")
        summary = reports.aggregate([a, a, b])
        self.assertEqual(summary["incident_count"], 2)
        self.assertEqual(summary["machine_count"], 2)
        self.assertEqual(summary["patterns"][0]["machine_count"], 2)
        self.assertTrue(summary["patterns"][0]["recurring"])

    def test_different_signals_are_not_conflated(self):
        self.programs[0]["crashes"].append({"pid": 101, "time": NOW - 9, "signal": "SIGABRT"})
        self.assertEqual(len(reports.aggregate([self.report()])["patterns"]), 2)

    def test_latest_export_supplies_status_for_same_incident(self):
        older = self.report()
        newer = copy.deepcopy(older)
        newer["generated_at"] += 60
        newer["events"][0]["status"] = "resolved"
        group = reports.aggregate([newer, older])["patterns"][0]
        self.assertEqual(group["occurrences"], 1)
        self.assertEqual(group["status_counts"], {"resolved": 1})

    def test_retention_window_and_future_events(self):
        self.programs[0]["crashes"] += [{"pid": 101, "time": NOW - 40 * 86400, "signal": "SIGSEGV"},
                                         {"pid": 102, "time": NOW + 1, "signal": "SIGSEGV"}]
        self.assertEqual(len(self.report()["events"]), 1)

    def test_custom_paths_are_pseudonymous(self):
        self.programs[0]["exe"] = "/home/alice/secret-customer/internal-tool"
        report = self.report()
        self.assertTrue(report["events"][0]["component"].startswith("private-"))
        self.assertNotIn("alice", json.dumps(report))
        self.assertNotIn("internal-tool", json.dumps(report))

    def test_malformed_unknown_schema_and_forged_fingerprints_fail(self):
        good = self.report()
        for bad in ({}, {**good, "schema": "other"}, {**good, "events": [None]},
                    {**good, "machine_id": "not a UUID"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                reports.aggregate([bad])
        bad = copy.deepcopy(good)
        bad["events"][0]["fingerprint"] = "0" * 64
        with self.assertRaises(ValueError):
            reports.validate(bad)

    def test_save_is_private_and_refuses_overwrite_or_symlink(self):
        target = self.root / "report.json"
        reports.save(target, self.report())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            reports.save(target, {})
        alias = self.root / "alias"
        alias.symlink_to(target)
        with self.assertRaises(FileExistsError):
            reports.save(alias, {})


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for key, value in (("STATE_DIR", self.root), ("CONFIG_FILE", self.root / "config.json")):
            mock = patch.object(lili, key, value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_redaction_preserves_error_evidence(self):
        text = 'error: disk full password="two words" token=SECRET api_key: abc Authorization: Bearer bearer-secret user@example.org 192.168.1.1'
        redacted = privacy.redact(text)
        for sensitive in ("two words", "SECRET", "abc", "bearer-secret", "user@example.org", "192.168.1.1"):
            self.assertNotIn(sensitive, redacted)
        self.assertIn("error: disk full", redacted)

    def test_private_key_and_url_credentials(self):
        text = '-----BEGIN RSA PRIVATE KEY-----\nSECRET\n-----END RSA PRIVATE KEY----- https://alice:pass@example.org'
        redacted = privacy.redact(text)
        self.assertNotIn("SECRET", redacted)
        self.assertNotIn("alice:pass", redacted)

    def test_default_local_preserves_existing_user_choice(self):
        self.assertEqual(lili.load_config()["agent"], "ollama")
        self.root.joinpath("config.json").write_text('{"agent":"codex"}')
        self.assertEqual(lili.load_config()["agent"], "codex")

    def script(self, settings, binary="/usr/bin/fake-ai"):
        with patch.object(lili, "load_config", return_value={**lili.DEFAULTS, **settings}), \
                patch.object(lili, "which", return_value=binary), patch.object(lili, "open_terminal") as terminal:
            lili.launch_agent("Test", "error: disk full token=PRIVATE")
        return terminal.call_args.args[1]

    def test_remote_launch_cancels_before_executing_agent(self):
        marker = self.root / "executed"
        fake = self.root / "fake-ai"
        fake.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        fake.chmod(0o700)
        script = self.script({"agent": "claude"}, str(fake))
        prompt = next(self.root.glob("prompt-*")).read_text()
        self.assertNotIn("PRIVATE", prompt)
        result = subprocess.run(["sh", "-c", script], input="\n", text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse(list(self.root.glob("prompt-*")))
        self.assertIn(privacy.remote_notice("Claude Code", translate=lili._), result.stdout)

    def test_remote_launch_executes_only_after_explicit_send(self):
        marker = self.root / "executed"
        fake = self.root / "fake-ai"
        fake.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        fake.chmod(0o700)
        script = self.script({"agent": "codex"}, str(fake))
        subprocess.run(["sh", "-c", script], input="SEND\n", text=True, capture_output=True, check=True)
        self.assertTrue(marker.exists())

    def test_local_launch_sets_up_missing_binary_without_remote_fallback(self):
        script = self.script({"agent": "ollama"}, None)
        self.assertIn("local setup || exit", script)
        self.assertIn("opencode", script)
        self.assertNotIn("lili_consent", script)
        self.assertNotIn("claude", script)

    def test_remote_ollama_also_requires_consent(self):
        script = self.script({"agent": "ollama", "ollama_url": "http://server.internal:11434"})
        self.assertIn("lili_consent", script)
        self.assertLess(script.index("lili_consent"), script.index("local setup"))

    def test_model_profile_is_versioned_and_instructions_are_not_training(self):
        name = lili.local_model_name(lili.DEFAULTS)
        with patch.object(lili, "LOCAL_SYSTEM", lili.LOCAL_SYSTEM + " changed"):
            self.assertNotEqual(name, lili.local_model_name(lili.DEFAULTS))
        self.assertIn("untrusted evidence", lili.LOCAL_SYSTEM)

    def test_setup_embeds_profile_in_ollama_create(self):
        with patch.object(lili, "load_config", return_value=lili.DEFAULTS), \
                patch.object(lili, "which", return_value="opencode"), \
                patch.object(lili, "ollama_models", return_value={lili.LOCAL_MODEL}), \
                patch.object(lili, "ollama", return_value=io.BytesIO(b'{"status":"success"}')) as api:
            lili.local_setup()
        self.assertEqual(api.call_args.args[1], "/api/create")
        self.assertEqual(api.call_args.args[2]["system"], lili.LOCAL_SYSTEM)

    def test_local_provider_is_allowlisted_and_web_lookup_denied(self):
        config = lili.opencode_config(lili.DEFAULTS)
        self.assertEqual(config["enabled_providers"], ["ollama"])
        self.assertEqual(config["share"], "disabled")
        self.assertEqual(config["permission"]["webfetch"], "deny")


if __name__ == "__main__":
    unittest.main()
