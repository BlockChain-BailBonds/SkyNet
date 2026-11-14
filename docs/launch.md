# SkyNet Main — GitHub Pages launch and acceptance

**Maintainer:** 918 Technologies; original integration attribution: Matthew Blake Ward.

## Confirmed failure and repair path (14 November 2026)

The last recorded main-branch deployment before this documentation change was [run 43567193636](https://github.com/BlockChain-BailBonds/SkyNet/actions/runs/43567193636). Application tests, public-source collection, and local static packaging completed. `actions/configure-pages@v5` failed with `Get Pages site failed: Not Found`. This is repository Pages provisioning, **not** a CERN dataset parsing failure or a generic backend outage.

The workflow now retains a `skynet-pages-ready` downloadable artifact **before** checking the Pages enablement gate. It validates required public files and the CERN metadata snapshot. This makes successful artifact assembly separately verifiable but does **not** publish a website if Pages has not been enabled.

## Required one-time administrator setting

1. Visit https://github.com/BlockChain-BailBonds/SkyNet/settings/pages while signed into an account with repository administration permission.
2. Under **Build and deployment**, set **Source → GitHub Actions**.
3. Do not use a suggested Pages template; `.github/workflows/pages.yml` is already committed.
4. Open https://github.com/BlockChain-BailBonds/SkyNet/actions/workflows/pages.yml and run `main` using **Run workflow**, or trigger a new main-branch push.
5. Verify success at `Configure existing GitHub Pages site`, `upload-pages-artifact`, and `deploy-pages` as separate steps. If it fails again, read the specific step log and do not report success.

Official instructions: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

The default `GITHUB_TOKEN` cannot provision Pages via `enablement: true`. That option requires another token with separate administrator-grade permissions, which is not appropriate to commit in workflow source. There is no reason to create an unrestricted PAT for a one-time setting.

## Deployment evidence gates

| Gate | Direct evidence | Scope of VERIFIED |
| --- | --- | --- |
| Source verification | Unit tests, manifest checksum, JS syntax all pass | Code only |
| Public-source collection | Timestamped snapshot with status, source URL, digest | Individual remote response only |
| Static bundle | `skynet-pages-ready` Actions artifact, path preflight | Packaged site only |
| Pages configuration | `configure-pages` passes | Pages site provisioned |
| Pages upload/deploy | Deployment job outputs actual URL | Published frontend |
| HTTPS check | Fetch actual URL, HTML and assets, status 200 | Public frontend reaches browser |
| Gateway | Public HTTPS authenticated /health and API test, WSS handshake, server logs | Specific external backend only |
| Pocket/RuView | Authenticated genuine device heartbeats and consent, hardware measurements | That sensor/session only |

CERN catalog results and HAARP diagnostic pages are **not** live instrument telemetry. No live detector control, satellite or camera operation, physical sensor enrollment, forecast accuracy or private gateway deployment follows from green Pages CI.

## Artifact troubleshooting

- If unit tests fail, fix the failed test before touching Pages settings.
- If `MANIFEST.sha256` fails, regenerate the hash for the modified tracked files; do not turn off verification.
- If public CERN endpoints fail, `--allow-blocked` preserves the source error and a safe non-live report.
- If `skynet-pages-ready` succeeds but `configure-pages` fails, enable Pages in repository Settings. A local artifact is not a served website.
- If Pages deploy succeeds but the browser 404s, use the exact Pages output URL, not a guessed path; inspect the project base path and generated `index.html`.
- If assets 404, confirm `static/`, `data/`, `agent/` and `docs/` exist in the staged artifact.
- If the operator console opens but source evidence is blocked, distinguish stale/missing snapshot from an active negative measurement.
- Avoid leaking credentials, private telemetry, or participants in public Pages or Actions artifacts.

## Rollback

Review the failing SHA and workflow logs, revert only the breaking change through a reviewed pull request, allow the previous passing Pages workflow to deploy, and repeat the external HTTPS check. Never remove evidence, consent or authentication checks to force a green job.
