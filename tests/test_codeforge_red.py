"""Independent adversarial challenge cases for Red Team acceptance."""
import unittest
from codeforge.policy import TASKS, Rejected, inspect_patch


def patch(path):
    return ("\n".join(["diff --git a/" + path + " b/" + path, "new file mode 100644",
                       "index 0000000..e69de29", "--- /dev/null", "+++ b/" + path,
                       "@@ -0,0 +1 @@", "+attack"]) + "\n").encode()


class CodeForgeRedTests(unittest.TestCase):
    def test_identity_and_policy_mutation_attempts_rejected(self):
        attempts = [".github/workflows/pages.yml", ".github/workflows/security-checks.yml",
                    "codeforge/policy.py", "codeforge/merge_gate.py", "server.py",
                    "static/assets/spin.js", "docs/security.md", "README.md"]
        for path in attempts:
            with self.subTest(path=path), self.assertRaises(Rejected):
                inspect_patch(patch(path), TASKS["docs-ops"])

    def test_no_promoting_forecast_repair_to_automerge(self):
        report = inspect_patch(patch("tests/test_spin_mvp.py"), TASKS["forecast-fixture"])
        self.assertFalse(report["auto_merge_candidate"])

    def test_no_multi_path_smuggling(self):
        with self.assertRaises(Rejected):
            inspect_patch(patch("docs/codeforge-notes/status.md") + patch("docs/security.md"), TASKS["docs-ops"])

    def test_no_huge_generated_files(self):
        with self.assertRaises(Rejected):
            inspect_patch(patch("docs/codeforge-notes/status.md") + b"A" * 70000, TASKS["docs-ops"])


if __name__ == "__main__":
    unittest.main()
