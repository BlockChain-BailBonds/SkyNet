"""Check fixed-task eligibility without giving the model GitHub write access."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from codeforge.policy import task_by_name, Rejected

REPOSITORY = "BlockChain-BailBonds/SkyNet"


def api(endpoint: str, token: str):
    if not endpoint.startswith("/repos/BlockChain-BailBonds/SkyNet/"):
        raise Rejected("INVALID_API_ENDPOINT")
    req = urllib.request.Request(
        "https://api.github.com" + endpoint,
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                 "User-Agent": "SkyNet-CodeForge/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise Rejected("GITHUB_API_UNAVAILABLE") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise Rejected("GITHUB_API_UNAVAILABLE") from exc


def eligible(task_name: str, token: str) -> dict:
    task = task_by_name(task_name)
    if not token:
        raise Rejected("MISSING_READ_TOKEN")
    branch = "codeforge/" + task.name
    status, _ = api("/repos/" + REPOSITORY + "/git/ref/heads/" + branch, token)
    if status != 404:
        raise Rejected("BRANCH_ALREADY_EXISTS_REVIEW_BEFORE_RETRY")
    status, pulls = api("/repos/" + REPOSITORY + "/pulls?state=open&per_page=100", token)
    if status != 200 or not isinstance(pulls, list) or len(pulls) >= 100:
        raise Rejected("OPEN_PR_COVERAGE_INCOMPLETE")
    if any(pr.get("head", {}).get("ref") == branch for pr in pulls):
        raise Rejected("TASK_PR_ALREADY_OPEN")
    return {"task": task.name, "branch": branch, "prompt": task.prompt,
            "auto_merge_candidate": task.auto_merge_class}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    try:
        outcome = eligible(args.task, os.getenv("GH_TOKEN", ""))
        outcome["ready"] = "true"
        print("CODEFORGE_READY: " + args.task)
    except Rejected as exc:
        outcome = {"ready": "false", "reason": str(exc)}
        print("CODEFORGE_BLOCKED: " + str(exc))
    with open(args.output, "a", encoding="utf-8") as output:
        for k in ("ready", "task", "branch", "prompt"):
            if k in outcome:
                output.write(k + "=" + str(outcome[k]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
