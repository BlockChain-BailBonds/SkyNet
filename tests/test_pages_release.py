"""Pages release checks; no network and no simulated deployment assertions."""
from pathlib import Path
import hashlib
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PagesReleaseTests(unittest.TestCase):
    def test_documented_source_and_pages_switch(self):
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn('Settings → Pages',readme)
        self.assertIn('CERN.CMS',readme)
        self.assertIn('GitHub Pages does not host persistent Python',readme)
        self.assertIn('skynet-pages-ready',readme)
        self.assertIn('direct',readme.lower())
    def test_readme_integrity_manifest(self):
        data=(ROOT/'README.md').read_bytes()
        sha=hashlib.sha256(data).hexdigest()
        manifest=(ROOT/'MANIFEST.sha256').read_text()
        self.assertIn(sha+'  README.md',manifest)
    def test_packaging_artifact_before_deploy_and_ui_assets(self):
        workflow=(ROOT/'.github/workflows/pages.yml').read_text()
        self.assertIn('cp index.html README.md _site/',workflow)
        self.assertLess(workflow.index('skynet-pages-ready'),workflow.index('actions/configure-pages@v5'))
        self.assertLess(workflow.index('Validate staged site and evidence'),workflow.index('actions/upload-pages-artifact@v4'))
        self.assertIn('static/assets/cern.js',workflow)
        self.assertIn('data/public/cern-status.json',workflow)
        self.assertIn('Full README',(ROOT/'index.html').read_text())
    def test_cern_markdown_valid_commands(self):
        cern=(ROOT/'docs/cern.md').read_text()
        self.assertIn('python3 -m forecast.cern --allow-blocked',cern)
        self.assertIn('`'+'``bash',cern)
        self.assertNotIn('\\`',cern)

if __name__=='__main__':
    unittest.main()
