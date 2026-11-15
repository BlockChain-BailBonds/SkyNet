"""Trusted CodeForge task catalog and strict Git patch admission gate.

This module is not writable by the coding agent. The caller checks out the
trusted base revision before applying any untrusted generated patch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_PATCH_BYTES = 65_536
MAX_FILE_BYTES = 12_288
MAX_FILES = 3
SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,160}$")
PATCH_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
MODE_CHANGES = ("old mode ", "new mode ", "deleted file mode ", "rename from ", "rename to ",
                "copy from ", "copy to ", "GIT binary patch", "Binary files ", "Submodule ")
CREDENTIALS = re.compile(
    r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"AIzaSy[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY",
    re.IGNORECASE,
)


class Rejected(ValueError):
    """A deterministic policy condition rejected the generated candidate."""


@dataclass(frozen=True)
class Task:
    name: str
    prompt: str
    allowed_paths: tuple[str, ...]
    auto_merge_class: bool
    max_changed_lines: int


TASKS = {
    "forecast-fixture": Task(
        name="forecast-fixture",
        prompt="codeforge/prompts/forecast-fixture.md",
        allowed_paths=("forecast/ingest.py", "tests/test_spin_mvp.py"),
        auto_merge_class=False,
        max_changed_lines=160,
    ),
    "docs-ops": Task(
        name="docs-ops",
        prompt="codeforge/prompts/docs-ops.md",
        allowed_paths=("docs/codeforge-notes/status.md",),
        auto_merge_class=True,
        max_changed_lines=100,
    ),
}


def task_by_name(name: str) -> Task:
    try:
        return TASKS[name]
    except (KeyError, TypeError) as exc:
        raise Rejected("TASK_NOT_ALLOWLISTED") from exc


def clean_path(name: str) -> bool:
    return (
        isinstance(name, str)
        and SAFE_PATH.fullmatch(name) is not None
        and not name.startswith((".git/", "/"))
        and not name.endswith(("/", "."))
        and all(part not in {"", ".", ".."} for part in name.split("/"))
    )


def inspect_patch(raw: bytes, task: Task) -> dict:
    """Admit text patches only; enforce allowlist before running git apply."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PATCH_BYTES or b"\x00" in raw:
        raise Rejected("PATCH_SIZE_OR_ENCODING")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Rejected("PATCH_SIZE_OR_ENCODING") from exc
    if "\r" in text or CREDENTIALS.search(text):
        raise Rejected("PATCH_CR_OR_CREDENTIAL")
    files = []
    changed = 0
    for line in text.splitlines():
        if line.startswith(MODE_CHANGES):
            raise Rejected("FILE_MODE_RENAME_OR_BINARY")
        if line.startswith("new file mode ") and line != "new file mode 100644":
            raise Rejected("UNSAFE_NEW_FILE_MODE")
        if line.startswith("diff --git "):
            match = PATCH_HEADER.fullmatch(line)
            if not match or match.group(1) != match.group(2):
                raise Rejected("UNSUPPORTED_PATCH_PATH")
            path = match.group(1)
            if not clean_path(path) or path not in task.allowed_paths or path in files:
                raise Rejected("PATH_OUTSIDE_TASK_ALLOWLIST")
            files.append(path)
        elif line.startswith(("+++", "---")):
            if not files:
                raise Rejected("MALFORMED_PATCH")
            expect = "+++ b/" if line.startswith("+++") else "--- a/"
            if line not in {expect + files[-1], "--- /dev/null"}:
                raise Rejected("UNEXPECTED_PATCH_TARGET")
        elif line.startswith(("+", "-")):
            if not line.startswith(("+++", "---")):
                changed += 1
    if not files or len(files) > MAX_FILES or changed == 0 or changed > task.max_changed_lines:
        raise Rejected("FILE_OR_CHANGE_LIMIT")
    return {
        "schema_version": "1.0", "task": task.name,
        "paths": files, "risk": "LOW_RISK_DOCUMENTATION" if task.auto_merge_class else "REVIEW_REQUIRED",
        "auto_merge_candidate": task.auto_merge_class,
        "lines_changed": changed, "patch_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def apply_candidate(raw: bytes, task: Task, root: Path) -> dict:
    report = inspect_patch(raw, task)
    for args in (["git", "apply", "--check", "--whitespace=error", "-"],
                 ["git", "apply", "--whitespace=error", "-"]):
        result = subprocess.run(args, input=raw, cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15, check=False)
        if result.returncode:
            raise Rejected("PATCH_APPLY_REJECTED")
    digests = {}
    for name in report["paths"]:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise Rejected("FILE_NOT_REGULAR_OR_TOO_LARGE")
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    report["file_sha256"] = digests
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = apply_candidate(args.patch.read_bytes(), task_by_name(args.task), args.root)
    except (Rejected, OSError, subprocess.TimeoutExpired) as exc:
        print("CODEFORGE_BLOCKED: " + (str(exc) if isinstance(exc, Rejected) else "IO_OR_TIMEOUT"))
        return 2
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.report:
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
