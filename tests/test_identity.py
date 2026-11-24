"""A crash is named after the program that ran it, not after any launcher sharing its binary."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("lili", str(Path(__file__).resolve().parents[1] / "bin/lili-crash"))
spec = importlib.util.spec_from_loader(loader.name, loader)
lili = importlib.util.module_from_spec(spec)
loader.exec_module(lili)

BROWSER = "/opt/brave-bin/brave"
WEB_APP = "brave-blgdilankhbcpipclgpdndahbehalgkh-Default"


class IdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.applications = Path(temp.name) / "applications"
        self.applications.mkdir()
        patcher = patch.object(lili, "data_dirs", return_value=[temp.name])
        patcher.start()
        self.addCleanup(patcher.stop)
        lili.desktop_entries.cache_clear()
        self.addCleanup(lili.desktop_entries.cache_clear)

    def desktop(self, app_id, name, command):
        (self.applications / f"{app_id}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nIcon={app_id}\nExec={command}\n", encoding="utf-8")

    def install_web_app(self):
        # Sorts before brave-browser.desktop, which is what made it win.
        self.desktop(WEB_APP, "Apple Music", f"{BROWSER} --profile-directory=Default --app-id=blgdilankhbcpipclgpdndahbehalgkh")

    def install_browser(self):
        self.desktop("brave-browser", "Brave", "brave %U")

    def test_escaped_service_unit_finds_its_own_launcher(self):
        self.install_web_app()
        self.install_browser()
        unit = r"app-brave\x2dbrowser@5a9efbd451b443528fed5a8a95b91f13.service"
        self.assertEqual(lili.identity("brave", BROWSER, unit), ("Brave", "brave-browser"))

    def test_binary_lookup_skips_web_apps(self):
        self.install_web_app()
        self.install_browser()
        self.assertEqual(lili.identity("brave", BROWSER, ""), ("Brave", "brave-browser"))

    def test_web_app_keeps_its_name_when_it_owns_the_unit(self):
        self.install_web_app()
        self.install_browser()
        unit = f"app-{WEB_APP}@5a9efbd451b443528fed5a8a95b91f13.service"
        self.assertEqual(lili.identity("brave", BROWSER, unit), ("Apple Music", WEB_APP))

    def test_only_web_apps_installed_falls_back_to_the_process_name(self):
        self.install_web_app()
        self.assertEqual(lili.identity("brave", BROWSER, ""), ("brave", "application-x-executable"))


if __name__ == "__main__":
    unittest.main()
