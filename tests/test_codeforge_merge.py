"""No-token unit tests for zero-bypass autonomous merge eligibility."""
import copy
import unittest
from codeforge.merge_gate import evaluate, REQUIRED_CHECKS, APPROVAL_LABEL


def example():
    sha = "a" * 40
    repo = {"full_name": "BlockChain-BailBonds/SkyNet", "default_branch": "main",
            "allow_auto_merge": True}
    pr = {
        "number": 24, "title": "CodeForge: docs-ops",
        "body": "[codeforge-task:docs-ops] [codeforge-patch-sha256:abc]",
        "state": "open", "draft": False, "mergeable": True, "changed_files": 1,
        "head": {"sha": sha, "ref": "codeforge/docs-ops",
                 "repo": {"full_name": "BlockChain-BailBonds/SkyNet"}},
        "base": {"ref": "main"}, "user": {"login": "github-actions[bot]"},
        "labels": [{"name": APPROVAL_LABEL}],
    }
    files = [{"filename": "docs/codeforge-notes/status.md", "status": "added", "changes": 10}]
    rules = [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 1,
                                                "require_last_push_approval": True}},
        {"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": x} for x in REQUIRED_CHECKS]}},
        {"type": "non_fast_forward"}, {"type": "deletion"},
    ]
    checks = [{"name": x, "status": "completed", "conclusion": "success",
               "head_sha": sha, "app": {"slug": "github-actions"},
               "started_at": "2026-11-14T00:00:00Z"} for x in REQUIRED_CHECKS]
    reviews = [{"user": {"login": "reviewer", "type": "User"}, "state": "APPROVED",
                "commit_id": sha, "submitted_at": "2026-11-14T00:05:00Z"}]
    return repo, pr, files, rules, checks, reviews


class MergeGateTests(unittest.TestCase):
    def test_require_all_controls_for_approval(self):
        args = example()
        self.assertTrue(evaluate(*args)["eligible"])

    def test_disabled_automerge_blocks(self):
        args = list(example())
        args[0]["allow_auto_merge"] = False
        r = evaluate(*args)
        self.assertFalse(r["eligible"])
        self.assertIn("GITHUB_AUTO_MERGE_DISABLED", r["reason_codes"])

    def test_missing_branch_rules_blocks(self):
        args = list(example())
        args[3] = []
        self.assertIn("PROTECTED_BRANCH_RULES_REQUIRED", evaluate(*args)["reason_codes"])

    def test_missing_approval_for_current_sha_blocks(self):
        args = list(example())
        args[5][0]["commit_id"] = "b" * 40
        self.assertIn("HUMAN_APPROVAL_FOR_CURRENT_HEAD_REQUIRED", evaluate(*args)["reason_codes"])

    def test_any_check_failure_blocks(self):
        args = list(example())
        args[4][0]["conclusion"] = "failure"
        self.assertFalse(evaluate(*args)["eligible"])

    def test_non_docs_patch_blocks_even_with_checks(self):
        args = list(example())
        args[2][0]["filename"] = "forecast/ingest.py"
        self.assertIn("PATH_OR_OPERATION_NOT_ALLOWLISTED", evaluate(*args)["reason_codes"])

    def test_forged_path_or_human_labels_block(self):
        args = list(example())
        args[1]["labels"] = []
        self.assertIn("OPERATOR_APPROVAL_LABEL_MISSING", evaluate(*args)["reason_codes"])
        args = list(example())
        args[1]["head"]["ref"] = "codeforge/forecast-fixture"
        self.assertIn("UNEXPECTED_BRANCH_OR_SHA", evaluate(*args)["reason_codes"])

    def test_unprotected_or_dismissed_review_blocks(self):
        args = list(example())
        args[3][0]["parameters"]["require_last_push_approval"] = False
        self.assertFalse(evaluate(*args)["eligible"])
        args = list(example())
        args[5][0]["state"] = "DISMISSED"
        self.assertFalse(evaluate(*args)["eligible"])


if __name__ == "__main__":
    unittest.main()
