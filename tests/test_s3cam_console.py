"""Execute the Node protocol regression suite in SkyNet's existing Python CI gate."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class S3CamConsoleProtocolTests(unittest.TestCase):
    def test_protocol_regressions(self):
        result = subprocess.run(
            ["node", "--test", "tests/test_s3cam_protocol.mjs"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_pages_module_is_complete(self):
        root = ROOT / "static" / "s3-cam-acceptance"
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="./app.mjs"', html)
        self.assertIn('href="./style.css"', html)
        for filename in ("protocol.mjs", "app.mjs", "style.css", "README.md"):
            self.assertTrue((root / filename).is_file(), filename)
        script = (root / "app.mjs").read_text(encoding="utf-8")
        self.assertIn("parseCaptureLog", script)
        self.assertIn("buildReport", script)
        self.assertNotIn("write_flash", script)
        self.assertNotIn("erase_flash", script)

if __name__ == "__main__":
    unittest.main()
