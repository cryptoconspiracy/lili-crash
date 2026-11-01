"""The AI opens in the user's own terminal when the desktop says which one it is."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("lili", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.bin = Path(temp.name)
        self.addCleanup(patch.stopall)

    def install(self, *names, xdg_dir=True):
        for name in names:
            path = self.bin / name
            body = '--dir=*) dir=${1#--dir=} ;;' if name == "xdg-terminal-exec" and xdg_dir else 'exec "$@"'
            path.write_text(f"#!/bin/sh\n{body}\n")
            path.chmod(0o755)
        patch.dict(os.environ, {"PATH": str(self.bin)}, clear=False).start()

    def chosen(self, desktop="GNOME", terminal="", choice="auto"):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop, "TERMINAL": terminal}):
            return lili.terminal_command(choice, "/work", "Title", ["sh", "launch.sh"])

    def test_the_default_terminal_comes_before_any_known_one(self):
        self.install("xdg-terminal-exec", "gnome-terminal", "alacritty")
        self.assertEqual(self.chosen(), ["xdg-terminal-exec", "--dir=/work", "--title=Title", "--", "sh", "launch.sh"])

    def test_terminal_variable_still_wins(self):
        self.install("xdg-terminal-exec", "kitty")
        self.assertEqual(self.chosen(terminal="/usr/bin/kitty")[0], "kitty")

    def test_plasma_keeps_konsole(self):
        self.install("xdg-terminal-exec", "konsole")
        self.assertEqual(self.chosen(desktop="KDE")[0], "konsole")

    def test_a_release_without_options_is_skipped(self):
        self.install("xdg-terminal-exec", "alacritty", xdg_dir=False)
        self.assertEqual(self.chosen()[0], "alacritty")
        self.assertEqual(lili.installed_terminals(), ["alacritty"])

    def test_a_missing_or_unknown_choice_falls_back(self):
        self.install("xdg-terminal-exec")
        self.assertEqual(self.chosen(choice="ptyxis")[0], "xdg-terminal-exec")
        self.assertEqual(self.chosen(choice="kitty")[0], "xdg-terminal-exec")


if __name__ == "__main__":
    unittest.main()
