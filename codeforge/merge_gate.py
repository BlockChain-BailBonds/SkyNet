"""Fail-closed GitHub PR merge eligibility evaluator.

The model cannot call this code with write credentials. A separate trusted
scheduled workflow uses it before enabling GitHub-native auto-merge.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from codeforge.policy import TASKS, Rejected

REPOSITORY = "BlockChain-BailBonds/SkyNet"
BASE = "/repos/" + REPOSITORY
REQUIRED_CHECKS = frozenset({
    "test (3.10)", "test (3.13)", "scan", "CodeForge Red", "CodeForge Blue",
})
APPROVAL_LABEL = "codeforge:low-risk-approved"


def evaluate(repo: dict, pr: dict, files: list, rules: list, checks: list,
             reviews: list) -> dict:
    """Return a machine-readable decision, no side effects or exceptions."""
    problems = []
    def deny(reason):
        if reason not in problems:
            problems.append(reason)

    task_name = "docs-ops"
    task = TASKS[task_name]
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    head_sha = head.get("sha")
    author = (pr.get("user") or {}).get("login", "")
    if not repo.get("allow_auto_merge"):
        deny("GITHUB_AUTO_MERGE_DISABLED")
    if repo.get("full_name") != REPOSITORY or repo.get("default_branch") != "main":
        deny("REPOSITORY_IDENTITY")
    if pr.get("state") != "open" or pr.get("draft") or pr.get("mergeable") is not True:
        deny("PR_NOT_MERGEABLE")
    if base.get("ref") != "main" or (head.get("repo") or {}).get("full_name") != REPOSITORY:
        deny("CROSS_REPOSITORY_OR_BASE")
    if head.get("ref") != "codeforge/" + task_name or not isinstance(head_sha, str) or len(head_sha) != 40:
        deny("UNEXPECTED_BRANCH_OR_SHA")
    if pr.get("title") != "CodeForge: docs-ops":
        deny("UNEXPECTED_PR_TITLE")
    body = pr.get("body") or ""
    if "[codeforge-task:docs-ops]" not in body or "[codeforge-patch-sha256:" not in body:
        deny("MISSING_PROVENANCE_MARKERS")
    if not author.endswith("[bot]"):
        deny("PR_NOT_AUTOMATION_AUTHORED")
    if APPROVAL_LABEL not in {x.get("name") for x in pr.get("labels", []) if isinstance(x, dict)}:
        deny("OPERATOR_APPROVAL_LABEL_MISSING")
    if not isinstance(files, list) or not files or len(files) > 2 or (pr.get("changed_files") or 0) != len(files):
        deny("FILES_NOT_FULLY_VERIFIED")
    else:
        for f in files:
            if f.get("filename") not in task.allowed_paths or f.get("status") not in {"added", "modified"}:
                deny("PATH_OR_OPERATION_NOT_ALLOWLISTED")
            if int(f.get("changes", 10000)) > task.max_changed_lines:
                deny("CHANGE_LIMIT")
    if not isinstance(rules, list) or len(rules) >= 100:
        deny("RULESET_COVERAGE_UNVERIFIED")
        rules = []
    kinds = {x.get("type") for x in rules if isinstance(x, dict)}
    if not {"pull_request", "required_status_checks", "non_fast_forward", "deletion"}.issubset(kinds):
        deny("PROTECTED_BRANCH_RULES_REQUIRED")
    review_rules = [r.get("parameters", {}) for r in rules if r.get("type") == "pull_request"]
    if not any(isinstance(r, dict) and r.get("required_approving_review_count", 0) >= 1
               and r.get("require_last_push_approval") is True for r in review_rules):
        deny("FRESH_REVIEW_RULE_REQUIRED")
    check_rules = [r.get("parameters", {}) for r in rules if r.get("type") == "required_status_checks"]
    required = set()
    for rule in check_rules:
        if isinstance(rule, dict):
            required.update(x.get("context") for x in rule.get("required_status_checks", [])
                            if isinstance(x, dict))
    if not REQUIRED_CHECKS.issubset(required):
        deny("MANDATORY_CHECKS_NOT_BRANCH_REQUIRED")
    latest = {}
    for c in checks if isinstance(checks, list) else []:
        if c.get("name") in REQUIRED_CHECKS:
            name = c["name"]
            if name not in latest or (c.get("started_at") or "") > (latest[name].get("started_at") or ""):
                latest[name] = c
    for name in REQUIRED_CHECKS:
        run = latest.get(name)
        if not run or run.get("status") != "completed" or run.get("conclusion") != "success" or (run.get("app") or {}).get("slug") != "github-actions" or (run.get("head_sha") not in {None, head_sha}):
            deny("REQUIRED_CHECK_NOT_PASSED:" + name)
    if not isinstance(reviews, list) or len(reviews) >= 100:
        deny("REVIEW_COVERAGE_UNVERIFIED")
        reviews = []
    current = {}
    for review in reviews:
        user = review.get("user") or {}
        name = user.get("login")
        if name and user.get("type") == "User" and name != author:
            if name not in current or (review.get("submitted_at") or "") > (current[name].get("submitted_at") or ""):
                current[name] = review
    approved = [r for r in current.values()
                if r.get("state") == "APPROVED" and r.get("commit_id") == head_sha]
    if not approved:
        deny("HUMAN_APPROVAL_FOR_CURRENT_HEAD_REQUIRED")
    return {
        "eligible": not problems,
        "reason_codes": sorted(problems),
        "head_sha": head_sha if isinstance(head_sha, str) else "",
        "pull_number": pr.get("number"),
        "merge_method": "squash",
        "policy": "LOW_RISK_DOCS_WITH_HUMAN_REVIEW_AND_REQUIRED_CHECKS",
    }


def github_get(path: str, token: str):
    if not path.startswith(BASE) or not token:
        raise Rejected("GITHUB_ACCESS_NOT_AUTHORIZED")
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "SkyNet-CodeForge-MergeGate/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise Rejected("REQUIRED_GITHUB_EVIDENCE_INACCESSIBLE") from exc


def inspect_live(number: int, token: str) -> dict:
    if not isinstance(number, int) or number <= 0:
        raise Rejected("INVALID_PR")
    repo = github_get(BASE, token)
    pr = github_get(BASE + "/pulls/" + str(number), token)
    files = github_get(BASE + "/pulls/" + str(number) + "/files?per_page=100", token)
    rules = github_get(BASE + "/rules/branches/main?per_page=100", token)
    checks = github_get(BASE + "/commits/" + str((pr.get("head") or {}).get("sha", "")) + "/check-runs?per_page=100", token)
    reviews = github_get(BASE + "/pulls/" + str(number) + "/reviews?per_page=100", token)
    return evaluate(repo, pr, files, rules, checks.get("check_runs", []), reviews)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        verdict = inspect_live(args.pr, os.environ.get("GH_TOKEN", ""))
    except Rejected as exc:
        verdict = {"eligible": False, "reason_codes": [str(exc)], "head_sha": "",
                   "pull_number": args.pr}
    args.out.write_text(json.dumps(verdict, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
