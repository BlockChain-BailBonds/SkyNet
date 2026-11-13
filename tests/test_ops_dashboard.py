"""Regression checks for the read-only SkyNet deployment evidence console."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "static" / "ops" / "index.html"


class OperatorEvidenceConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = OPS.read_text(encoding="utf-8")

    def test_is_bundled_from_static_directory(self):
        self.assertTrue(OPS.is_file())
        self.assertIn("SkyNet Main | Deployment Evidence Console", self.html)
        self.assertIn("data-tab=\"overview\"", self.html)
        self.assertIn("data-tab=\"network\"", self.html)
        self.assertIn("data-tab=\"pocket\"", self.html)
        self.assertIn("data-tab=\"evidence\"", self.html)
        self.assertIn("data-tab=\"tests\"", self.html)

    def test_explicit_evidence_boundaries(self):
        for text in (
            "VERIFIED", "UNVERIFIED", "BLOCKED", "FAILED",
            "Do not infer live ingestion",
            "No telemetry is sent",
            "No background monitoring",
            "static",
            "device-enrollment.md",
        ):
            self.assertIn(text, self.html)
        self.assertIn('else if(x.conclusion==="failure")', self.html)
        self.assertIn('current(x)', self.html)
        self.assertIn('function stale(x)', self.html)

    def test_no_browser_persistent_secret_storage(self):
        for prohibited in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            self.assertNotIn(prohibited, self.html)
        self.assertIn('$("credential").value=""', self.html)
        self.assertIn('const headers=credentialHeaders();', self.html)
        self.assertIn('async function authGet(pathId,sharedHeaders)', self.html)
        self.assertIn('u.hash||u.search', self.html)

    def test_read_only_network_methods(self):
        self.assertIn('method:"GET"', self.html)
        self.assertIn('new WebSocket(u.href)', self.html)
        self.assertNotIn('method:"POST"', self.html)
        self.assertNotIn('method:"PUT"', self.html)
        self.assertNotIn('method:"DELETE"', self.html)
        self.assertIn('redirect:"error"', self.html)

    def test_embedded_script_syntax(self):
        match = re.search(r"<script>([\s\S]*?)</script>", self.html)
        self.assertIsNotNone(match)
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator-console.js"
            path.write_text(match.group(1), encoding="utf-8")
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True, text=True, check=False, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
