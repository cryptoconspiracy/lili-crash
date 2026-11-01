"""Failed launches must be read from the journal once, not on every refresh."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("lili", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)

APP = "a" * 32
LOOP = "b" * 32


def entry(cursor, usec, **fields):
    return json.dumps({"__CURSOR": cursor, "__REALTIME_TIMESTAMP": str(usec), **fields})


class Journal:
    """Answers the three queries failed_launches makes, and records them."""

    def __init__(self):
        self.failed = [
            entry("c1", 10_000_000, USER_UNIT="ydotoold.service", USER_INVOCATION_ID=LOOP),
            entry("c2", 20_000_000, USER_UNIT="app-org.example.Broken@1a2b.service", USER_INVOCATION_ID=APP),
        ]
        self.calls = []
        self.bad_cursor = False

    def run(self, argv, **_kwargs):
        self.calls.append(argv)
        out, code = [], 0
        if f"MESSAGE_ID={lili.UNIT_FAILED_MESSAGE_ID}" in argv:
            after = next((a.split("=", 1)[1] for a in argv if a.startswith("--after-cursor=")), None)
            if after and self.bad_cursor:
                code = 1
            else:
                cursors = [json.loads(e)["__CURSOR"] for e in self.failed]
                out = self.failed[cursors.index(after) + 1:] if after else self.failed
        elif f"MESSAGE_ID={lili.UNIT_STARTED_MESSAGE_ID}" in argv:
            out = [entry("s1", 15_000_000, USER_INVOCATION_ID=APP)]
        elif f"MESSAGE_ID={lili.UNIT_EXITED_MESSAGE_ID}" in argv:
            out = [entry("e1", 19_000_000, USER_INVOCATION_ID=APP, EXIT_STATUS="127")]
        return subprocess.CompletedProcess(argv, code, "\n".join(out) + "\n", "")

    def queries(self, message_id):
        return [c for c in self.calls if f"MESSAGE_ID={message_id}" in c]


class LaunchCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file = Path(temp.name) / "launches.json"
        self.journal = Journal()
        for mock in (patch.object(lili, "LAUNCHES_FILE", self.file),
                     patch.object(lili.subprocess, "run", side_effect=self.journal.run)):
            mock.start()
            self.addCleanup(mock.stop)

    def test_first_read_finds_the_launch_and_remembers_the_cursor(self):
        runs = lili.failed_launches()
        self.assertEqual([(r["id"], r["app"], r["seconds"], r["status"]) for r in runs],
                         [(f"launch-{APP}", "org.example.Broken", 5, "127")])
        self.assertEqual(json.loads(self.file.read_text())["cursor"], "c2")

    def test_later_reads_start_after_the_cursor_and_keep_what_was_found(self):
        lili.failed_launches()
        self.journal.calls.clear()
        runs = lili.failed_launches()
        self.assertEqual(len(runs), 1)
        self.assertIn("--after-cursor=c2", self.journal.queries(lili.UNIT_FAILED_MESSAGE_ID)[0])
        # Nothing new failed, so there is nothing to look up and nothing to save.
        self.assertEqual(self.journal.queries(lili.UNIT_STARTED_MESSAGE_ID), [])

    def test_a_cursor_the_journal_rejects_reads_everything_again(self):
        lili.failed_launches()
        self.journal.bad_cursor = True
        self.journal.calls.clear()
        runs = lili.failed_launches()
        self.assertEqual(len(runs), 1)
        reads = self.journal.queries(lili.UNIT_FAILED_MESSAGE_ID)
        self.assertEqual(len(reads), 2)
        self.assertFalse(any(a.startswith("--after-cursor") for a in reads[1]))

    def test_only_other_services_failing_skips_the_start_lookup(self):
        self.journal.failed = self.journal.failed[:1]
        self.assertEqual(lili.failed_launches(), [])
        self.assertEqual(self.journal.queries(lili.UNIT_STARTED_MESSAGE_ID), [])
        self.assertEqual(json.loads(self.file.read_text())["cursor"], "c1")


if __name__ == "__main__":
    unittest.main()
