"""Deterministic security and integrity tests for CodeForge patch admission."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from codeforge.policy import Rejected, TASKS, clean_path, inspect_patch, apply_candidate


def make_patch(path="docs/codeforge-notes/status.md", content="SkyNet status\n"):
    lines = content.splitlines()
    return ("\n".join([
        "diff --git a/" + path + " b/" + path,
        "new file mode 100644",
        "index 0000000..e69de29",
        "--- /dev/null",
        "+++ b/" + path,
        "@@ -0,0 +1," + str(len(lines)) + " @@",
        *("+" + line for line in lines),
    ]) + "\n").encode()


class CodeForgePolicyTests(unittest.TestCase):
    def test_catalog_fixed_and_automerge_docs_only(self):
        self.assertEqual(set(TASKS), {"forecast-fixture", "docs-ops"})
        self.assertTrue(TASKS["docs-ops"].auto_merge_class)
        self.assertFalse(TASKS["forecast-fixture"].auto_merge_class)
        self.assertTrue(all(x.startswith("docs/codeforge-notes/") for x in TASKS["docs-ops"].allowed_paths))

    def test_path_traversal_and_hidden_entries_blocked(self):
        for value in ("../../.github/workflows/pages.yml", "docs/../.github/x", ".git/hooks/pre-commit",
                      "/etc/passwd", "docs//bad.md", "docs/codeforge-notes/evil name.md", "docs/codeforge-notes/."):
            self.assertFalse(clean_path(value), value)
        with self.assertRaises(Rejected):
            inspect_patch(make_patch(".github/workflows/pages.yml"), TASKS["docs-ops"])

    def test_bounded_docs_patch_and_review_path(self):
        report = inspect_patch(make_patch(), TASKS["docs-ops"])
        self.assertTrue(report["auto_merge_candidate"])
        self.assertEqual(report["paths"], ["docs/codeforge-notes/status.md"])
        self.assertEqual(report["patch_sha256"], hashlib.sha256(make_patch()).hexdigest())
        with self.assertRaises(Rejected):
            inspect_patch(make_patch("forecast/ingest.py"), TASKS["docs-ops"])

    def test_reject_symlink_binary_rename_secret(self):
        valid = make_patch()
        for raw in (
            valid.replace(b"new file mode 100644", b"new file mode 120000"),
            valid.replace(b"new file mode 100644", b"rename from other.md"),
            valid + b"GIT binary patch\n",
            valid + b"\x00",
            valid.replace(b"SkyNet status", b"github_pat_" + b"x" * 25),
            valid * 4000,
        ):
            with self.assertRaises(Rejected):
                inspect_patch(raw, TASKS["docs-ops"])

    def test_git_apply_is_real_and_receipt_is_hash_linked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "README.md").write_text("baseline\n")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=CodeForgeTest", "-c", "user.email=test@example.test",
                            "commit", "-qm", "baseline"], cwd=root, check=True)
            result = apply_candidate(make_patch(), TASKS["docs-ops"], root)
            self.assertEqual(result["file_sha256"]["docs/codeforge-notes/status.md"],
                             hashlib.sha256(b"SkyNet status\n").hexdigest())
            with self.assertRaises(Rejected):
                apply_candidate(make_patch(), TASKS["docs-ops"], root)

    def test_user_supplied_task_cannot_expand_policy(self):
        from codeforge.policy import task_by_name
        for value in ("", "main", "docs-ops/../../main", "security-fix", "../docs-ops"):
            with self.assertRaises(Rejected):
                task_by_name(value)


if __name__ == "__main__":
    unittest.main()
