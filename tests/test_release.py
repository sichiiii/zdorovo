import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_is_consistent(self):
        source = (ROOT / "healthbreak.py").read_text()
        version = re.search(r'^APP_VERSION = "([^"]+)"$', source, re.MULTILINE).group(1)
        self.assertTrue((ROOT / "debian" / "changelog").read_text().startswith(f"zdorovo ({version})"))
        self.assertIn(
            f'version="{version}"', (ROOT / "data" / "io.github.jabka.Zdorovo.metainfo.xml").read_text()
        )
        self.assertIn(f"release-{version}", (ROOT / "README.md").read_text())

    def test_desktop_icon_is_packaged(self):
        desktop = (ROOT / "data" / "io.github.jabka.Zdorovo.desktop").read_text()
        self.assertIn("Icon=io.github.jabka.Zdorovo-mint-v2", desktop)
        self.assertTrue((ROOT / "assets" / "io.github.jabka.Zdorovo.svg").is_file())
        self.assertIn("io.github.jabka.Zdorovo-mint-v2.svg", (ROOT / "debian" / "links").read_text())

    def test_runtime_dependencies_cover_cairo_bridge(self):
        control = (ROOT / "debian" / "control").read_text()
        self.assertIn("python3-gi-cairo", control)
        self.assertIn("gir1.2-ayatanaappindicator3-0.1", control)

    def test_cyberjabka_credit_is_present(self):
        website = "https://cyberjabka.by/"
        self.assertIn(website, (ROOT / "healthbreak.py").read_text())
        self.assertIn(website, (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
