"""Static SkyNet design-contract and Pages UI integrity checks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DesignContractTests(unittest.TestCase):
    def test_design_contract_and_review_cover_all_twelve(self):
        design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
        review = (ROOT / "docs" / "ui-repository-review.md").read_text(encoding="utf-8")
        self.assertIn("VERIFIED", design)
        self.assertIn("UNVERIFIED", design)
        self.assertIn("GitHub Pages is a static frontend only", design)
        repos = [
            "nextlevelbuilder/ui-ux-pro-max-skill",
            "VoltAgent/awesome-design-md",
            "nexu-io/open-design",
            "Leonxlnx/taste-skill",
            "pbakaus/impeccable",
            "DavidHDev/react-bits",
            "emilkowalski/skills",
            "Nutlope/hallmark",
            "google-labs-code/design.md",
            "greensock/gsap-skills",
            "oso95/scroll-world",
            "DavidHDev/canvas-ui",
        ]
        for repo in repos:
            with self.subTest(repository=repo):
                self.assertIn(repo, review)

    def test_lightweight_ui_polish_loaded_after_existing_styles(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertLess(page.index("./static/assets/spin.css"), page.index("./static/assets/ui-polish.css"))
        self.assertLess(page.index("./static/assets/cern.css"), page.index("./static/assets/ui-polish.css"))
        self.assertIn('id="workspace"', page)
        self.assertIn('aria-label="Application views"', page)
        self.assertIn('data-view="pocket"', page)
        self.assertIn("./static/assets/spin.js", page)

    def test_touch_focus_and_reduced_motion_are_preserved(self):
        css = (ROOT / "static" / "assets" / "ui-polish.css").read_text(encoding="utf-8")
        for required in ("focus-visible", "min-height: 44px", "prefers-reduced-motion", "overflow-wrap: anywhere"):
            with self.subTest(required=required):
                self.assertIn(required, css)
        self.assertNotIn("@import", css)
        self.assertNotIn("url(", css)

if __name__ == "__main__":
    unittest.main()
