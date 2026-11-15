"""Deterministic real-Git integration tests for CodeForge's trust boundary.

This is not a real model run and never uses an API key or production GitHub
writes. The final merge verdict must remain BLOCKED without branch protection.
"""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from codeforge.merge_gate import evaluate
from codeforge.policy import TASKS, Rejected, apply_candidate
from codeforge.pr_guard import validate_branch


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=12).stdout.decode("utf-8").strip()


def workspace(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.name", "CodeForge test")
    git(root, "config", "user.email", "offline-test@example.invalid")
    (root / "README.md").write_text("Protected baseline\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "baseline")
    git(root, "branch", "-M", "main")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", sha)
    return sha


class EndToEndTests(unittest.TestCase):
    def test_docs_candidate_red_blue_receipts_and_merge_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, clean = Path(tmp) / "original", Path(tmp) / "clean"
            workspace(original)
            workspace(clean)
            git(original, "checkout", "-qb", "codeforge/docs-ops")
            path = original / "docs/codeforge-notes/status.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# SkyNet operations\n\nRead-only public status.\n",
                            encoding="utf-8")
            git(original, "add", "docs/codeforge-notes/status.md")
            git(original, "commit", "-qm", "bounded docs change")
            diff = subprocess.run(["git", "diff", "--binary", "--no-ext-diff",
                                   "origin/main...HEAD"], cwd=original, check=True,
                                  stdout=subprocess.PIPE, timeout=12).stdout
            red = validate_branch("docs-ops", original)
            blue = apply_candidate(diff, TASKS["docs-ops"], clean)
            self.assertEqual(red["patch_sha256"], blue["patch_sha256"])
            self.assertEqual(red["patch_sha256"], hashlib.sha256(diff).hexdigest())
            self.assertEqual(blue["file_sha256"]["docs/codeforge-notes/status.md"],
                             hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(blue["auto_merge_candidate"])

            head_sha = git(original, "rev-parse", "HEAD")
            pr = {"number": 81, "state": "open", "draft": False, "mergeable": True,
                  "title": "CodeForge: docs-ops",
                  "body": "[codeforge-task:docs-ops] [codeforge-patch-sha256:"
                          + red["patch_sha256"] + "]",
                  "changed_files": 1,
                  "head": {"sha": head_sha, "ref": "codeforge/docs-ops",
                           "repo": {"full_name": "BlockChain-BailBonds/SkyNet"}},
                  "base": {"ref": "main"}, "user": {"login": "github-actions[bot]"},
                  "labels": [{"name": "codeforge:low-risk-approved"}]}
            repo = {"full_name": "BlockChain-BailBonds/SkyNet",
                    "default_branch": "main", "allow_auto_merge": False}
            items = [{"filename": "docs/codeforge-notes/status.md",
                      "status": "added", "changes": 3}]
            decision = evaluate(repo, pr, items, [], [], [])
            self.assertFalse(decision["eligible"])
            self.assertIn("GITHUB_AUTO_MERGE_DISABLED", decision["reason_codes"])
            self.assertIn("PROTECTED_BRANCH_RULES_REQUIRED", decision["reason_codes"])

    def test_red_rejects_active_html_in_allowed_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "candidate"
            workspace(root)
            git(root, "checkout", "-qb", "codeforge/docs-ops")
            path = root / "docs/codeforge-notes/status.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<script>alert(1)</script>\n", encoding="utf-8")
            git(root, "add", "docs/codeforge-notes/status.md")
            git(root, "commit", "-qm", "attempted active content")
            with self.assertRaisesRegex(Rejected, "ACTIVE_CONTENT_IN_MARKDOWN"):
                validate_branch("docs-ops", root)

    def test_forecast_candidate_is_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "candidate"
            workspace(root)
            git(root, "checkout", "-qb", "codeforge/forecast-fixture")
            path = root / "tests/test_spin_mvp.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_fixture():\n    assert True\n", encoding="utf-8")
            git(root, "add", "tests/test_spin_mvp.py")
            git(root, "commit", "-qm", "forecast fixture candidate")
            result = validate_branch("forecast-fixture", root)
            self.assertFalse(result["auto_merge_candidate"])
            self.assertEqual(result["risk"], "REVIEW_REQUIRED")

    def test_coding_job_cannot_directly_merge_main(self):
        root = Path(__file__).resolve().parents[1]
        worker = (root / ".github/workflows/codeforge.yml").read_text()
        controller = (root / ".github/workflows/codeforge-merge.yml").read_text()
        self.assertIn("sandbox: workspace-write", worker)
        self.assertIn("persist-credentials: false", worker)
        self.assertIn("needs: [preflight, generate, red, blue]", worker)
        self.assertIn("gh pr create --head", worker)
        self.assertNotIn("gh pr merge", worker)
        self.assertIn("ref: main", controller)
        self.assertIn("python3 -m codeforge.merge_gate", controller)
        self.assertIn("--match-head-commit", controller)


if __name__ == "__main__":
    unittest.main()
