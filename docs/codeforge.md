# SkyNet CodeForge — Autonomous Engineering With Guarded Merge

**Original integration: Matthew Blake Ward, in association with 918 Technologies.**

## Release status

This subsystem is proposed on a feature branch and remains **UNVERIFIED as an operational autonomous coding service** until merged, configured, triggered and observed through GitHub Actions. Passing offline tests validates only the code and guardrails. GitHub Pages continues to host the public frontend, not the coding process.

## Architecture

1. A trusted preflight job maps a manually chosen task or a failed forecast workflow to one of exactly two committed task definitions. It checks for an existing CodeForge task branch and rejects duplicates.
2. A disposable runner checks out a pinned SkyNet revision without persisted Git credentials. The official OpenAI Codex action runs with workspace-limited filesystem permissions and sudo dropped. The AI may write a patch locally but receives no GitHub repository write token or production deployment credential.
3. A generated text diff is uploaded as a time-limited artifact.
4. The independent Red job validates patch boundaries, disallowed paths, dangerous document content and adversarial policy tests. The independent Blue job applies the same patch on a separate checkout and runs the repository regression suite inside a non-root, read-only, networkless container.
5. Only after both jobs pass can a separate write-enabled publisher revalidate the patch, check the base commit is current and create a new CodeForge branch and PR. It cannot push to main.
6. A separate scheduled merge controller runs from trusted main, reads actual GitHub PR/review/checks/rules evidence and uses native auto-merge only for the strict docs-only task if all conditions pass.

## Fixed task catalog

| Task | Files the agent may change | Risk class | Autonomous merge eligible |
| --- | --- | --- | --- |
| forecast-fixture | forecast/ingest.py, tests/test_spin_mvp.py | REVIEW_REQUIRED | No |
| docs-ops | docs/codeforge-notes/status.md | LOW_RISK_DOCUMENTATION | Conditional |

The forecast-fixture task targets a real observed Actions failure (workflow run 43567327514) in which a fixture-status assertion failed after successful USGS/NWS ingestion. Forecast repairs never auto-merge.

The docs-ops task produces a bounded plain-Markdown engineering note. No other documentation file can be auto-merged. This path is served as public data by GitHub Pages, so review and sanitization remain mandatory.

## Operator setup

1. Keep GitHub Pages deployed using the existing main deployment workflow.
2. In repository Settings → Secrets and variables → Actions, add the secret named **OPENAI_API_KEY** from an OpenAI API project with an appropriate budget. Do not embed the secret in source, GitHub Pages HTML, PR bodies, model output or browser storage.
3. In Actions, open **SkyNet CodeForge - Isolated Self-Coding** and select Run workflow. Choose forecast-fixture for the known failing workflow test or docs-ops for the low-risk documentation path.
4. Read the patch artifact, Red evidence, Blue evidence and generated PR. The artifact and check history are evidence of code activity, not production behavior.
5. Use the CodeForge read-only operator page linked from SkyNet Main to inspect GitHub PRs and workflow status. It has no privileged controls or persistent operator credentials.

When the Refresh bounded official snapshots workflow fails on main, CodeForge can also propose the forecast-fixture task automatically. A missing API secret, unavailable provider, already-existing task branch, source-policy failure or failed test blocks PR publication. Actions scheduling is best-effort and not an always-on process.

## Enabling narrowly scoped auto-merge

The initial repository inspection reported auto-merge disabled and no active rulesets. These states make the merge controller **BLOCKED** by design. Do not bypass protections to force merging.

An administrator must configure an active ruleset targeting main that requires a pull request, at least one human review, approval after the most recent push, required successful checks, prevention of force pushes and deletion. Configure exact required checks: test (3.10), test (3.13), scan, CodeForge Red and CodeForge Blue. Then enable Allow auto-merge in repository General settings.

For each docs-ops candidate, a human with write access must apply **codeforge:low-risk-approved**, and a separate human reviewer must approve the latest exact commit. An approved older commit, dismissed review, missing checks, missing rules, foreign branch or unauthorized path makes the decision fail closed. The controller reads branch rules from GitHub and refuses to infer protection from a green build.

Only then may the trusted **CodeForge low-risk auto-merge controller** schedule GitHub native squash auto-merge for codeforge/docs-ops, with a head-commit SHA lease. Native GitHub branch rules remain the final enforcement layer. The coding job never gets a merge credential.

**No unattended merges are authorized for application code, workflows, tests, security policy, API gateways, forecast algorithms, sensors, model weights or firmware.** Their PRs require explicit operator merge action.

## Validation and reproducibility

    python3 -m unittest tests.test_codeforge_policy -v
    python3 -m unittest tests.test_codeforge_red -v
    python3 -m unittest tests.test_codeforge_merge -v
    python3 -m unittest discover -s tests -v
    sha256sum -c MANIFEST.sha256

Local patch admission for an independently obtained code patch:

    python3 -m codeforge.policy --task docs-ops --patch /tmp/codeforge.patch

Patch receipts include task, risk class, changed paths, patch SHA-256, file digests and changed-line bounds. GitHub Actions links and Red/Blue test outcomes are retained with each generated PR. SHA-256 helps identify bytes but cannot by itself attest scientific truth, a trusted reviewer, signed evidence or model correctness.

## Safety notes

- No user-submitted free-form prompt is executed as a coding task.
- No workflow triggered by an untrusted PR executes model-authored scripts with write credentials.
- The Codex workspace permission profile and token separation are distinct controls. A failure in one must not grant additional privileges elsewhere.
- GitHub default-token-created PRs do not automatically trigger normal pull_request workflows. The publisher explicitly dispatches the CI, security and CodeForge review workflows on the new branch; their success must be observed independently.
- The static browser page uses read-only public GitHub endpoints without tokens; it may be rate limited or unavailable.
- If the branch protection endpoint is not readable, the rules endpoint is incomplete, or review/check sources are uncertain, CodeForge refuses auto-merge.
- The trusted Dockerfile is constructed before executing candidate tests with no network; its image build is a separate supply-chain input that should be pinned/reviewed for production.
- All original SkyNet Pages CI, sensor consent and source provenance controls remain in place.
