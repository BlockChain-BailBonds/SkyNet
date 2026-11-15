# CodeForge first-task acceptance gate

CodeForge has deterministic end-to-end fixture tests in
tests/test_codeforge_e2e.py. They create disposable local Git repositories,
produce actual git-diff patch bytes, enforce the exact docs and forecast task
allowlists, compare separate Red and Blue hashes, reject script-bearing
Markdown, and require the merge evaluator to block an otherwise eligible PR
when settings and rules are absent.

These are explicitly **offline integration tests**, not an actual Codex
coding job, a real GitHub code-generation PR, or an autonomous merge.
They require no secrets or network and can be executed in CI on the
feature PR before CodeForge is approved for main.

## Verification

Run from the SkyNet repository root:

    python3 -m unittest tests.test_codeforge_e2e -v
    python3 -m unittest discover -s tests -v

## First genuine coding task (after reviewed merge)

1. Configure an OpenAI API project key as the encrypted GitHub Actions secret
   OPENAI_API_KEY. Never add it to the repository or browser frontend.
2. In repository Settings → Actions → General, allow Actions to create PRs.
3. Run SkyNet CodeForge - Isolated Self-Coding, task forecast-fixture.
4. Verify a real model action run, SHA-256 patch artifact, independent Red and
   Blue evidence, bounded review-only PR, and separate GitHub CI checks.
5. Manually review and decide the forecast PR; it is not eligible for the
   autonomous merge controller.

Only after proving the first worker should docs-ops be considered for
protected auto-merge. That requires GitHub-native auto-merge, active main
rulesets, seven required checks, operator label, and a human approval tied to
the PR's current head SHA.

A green CodeForge fixture test cannot be reported as live coding,
validated model training, production deployment or physical sensor evidence.
