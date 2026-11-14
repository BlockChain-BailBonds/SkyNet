"""Independent Red static audit for CodeForge-generated branches.

Any non-CodeForge branch is simply excluded from automatic merging.
"""
import argparse
import re
import subprocess
from pathlib import Path
from codeforge.policy import task_by_name, inspect_patch, Rejected

DANGEROUS_MD = re.compile(
    r"<\s*(?:script|iframe|object|embed|style|svg)|"
    r"javascript\s*:|data\s*:|on(?:error|load|click)\s*=|"
    r"!\[[^\]]*\]\(\s*https?://",
    re.IGNORECASE,
)


def validate_branch(task_name: str, root: Path) -> dict:
    task = task_by_name(task_name)
    diff = subprocess.run(["git", "diff", "--binary", "--no-ext-diff", "origin/main...HEAD"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=root, timeout=15, check=True).stdout
    report = inspect_patch(diff, task)
    for path in report["paths"]:
        target = root / path
        if target.is_symlink() or not target.is_file():
            raise Rejected("NON_REGULAR_TARGET")
        if target.stat().st_size > 12_288:
            raise Rejected("TARGET_TOO_LARGE")
        if task.auto_merge_class:
            data = target.read_text(encoding="utf-8")
            if DANGEROUS_MD.search(data):
                raise Rejected("ACTIVE_CONTENT_IN_MARKDOWN")
    return report


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args(argv)
    try:
        report = validate_branch(args.task, args.root)
    except (Rejected, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print("CODEFORGE_RED_BLOCKED: " + (str(exc) if isinstance(exc, Rejected) else "VALIDATION_ERROR"))
        return 2
    print("CODEFORGE_RED_VERIFIED: " + report["patch_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
