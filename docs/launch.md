# SkyNet Main — launch runbook and release gates

**Owner:** Matthew Blake Ward, in association with 918 Technologies

**Deployment contract:** The public site is a **static operator frontend**, not
an internet-facing data acquisition gateway. No live RuView ingestion, camera
access, satellite detection, enrolled ESP32, or backend success may be claimed
without direct logs from that exact component.

## Current blocker (observed 2026-11-13 UTC)

- GitHub repository: `BlockChain-BailBonds/SkyNet`, branch `main`.
- A source validation run completed successfully for main commit
  `cad9aeed8e278e1821dd2432095aeb22adf62a14`.
- GitHub Pages run `43528907765` **FAILED** at
  `actions/configure-pages@v5` after tests and site packaging passed.
- Job `132241450929` reports:
  `Get Pages site failed: Not Found`, followed by
  `Create Pages site failed: Resource not accessible by integration`.
- The workflow was using `enablement: true`; the default
  `GITHUB_TOKEN` cannot enable Pages. This patch removes that ineffective
  request. No credential workaround is required or recommended.

## Required single owner action

1. Sign into GitHub with administrator access to
   https://github.com/BlockChain-BailBonds/SkyNet/settings/pages
2. Under **Build and deployment**, select **GitHub Actions** as **Source**.
   This creates/enables the Pages site. Do not create a second workflow from a
   template; this repository already includes `.github/workflows/pages.yml`.
3. From
   https://github.com/BlockChain-BailBonds/SkyNet/actions/workflows/pages.yml
   choose **Run workflow** on `main`, or push a reviewed change to `main`.
4. Confirm green **Publish SkyNet Main to GitHub Pages** workflow, including
   `configure-pages`, `upload-pages-artifact`, and `deploy-pages`.
5. Open the **Pages-provided site URL** and verify HTTPS, 200 response,
   application assets, forecast panel, and health/consent labels. For the
   standard project-site URL, use
   https://blockchain-bailbonds.github.io/SkyNet/ **only after GitHub confirms
   it**. A code push or green source tests alone are insufficient.

Reference:
https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## Deployment gates

| Gate | Required direct evidence | Success label |
| --- | --- | --- |
| 1. Source/test | GitHub Actions tests and browser syntax pass | VERIFIED (code only) |
| 2. Pages artifact | Pages workflow publishes content successfully | VERIFIED (deployment) |
| 3. HTTPS frontend | GET /SkyNet and key assets return expected bytes over HTTPS | VERIFIED (frontend) |
| 4. Data freshness | Embedded source timestamp, digest, source link, and successful data-fetch trace | VERIFIED (source access only) |
| 5. Backend | Public HTTPS /health, authenticated API request, WSS handshake + server logs | VERIFIED (backend only) |
| 6. Pocket | Approved device ID, authenticated heartbeat, timestamp, nonce/replay checks | VERIFIED (one enrolled device) |
| 7. RuView | Real authorized hardware source, runtime logs, calibration + signed-frame verification | VERIFIED (specific measurement only) |
| 8. HAARP | Official public diagnostics response, source hash; numeric measurement only after verified parsing and units | VERIFIED for catalog, UNVERIFIED for measurement |

A BLOCKED source must remain BLOCKED. A publicly reachable Pages frontend must
never be presented as a real sensor gateway. Never fake or seed a sensor state
as successful field evidence. Keep exact source and measured-vs-simulated labels.

## Backend deployment

The source tree contains an optional local Python gateway (`server.py`) and
the separate Chimera backend candidate (`chimera/backend`). Neither is an
implicitly deployed HTTPS/WSS production gateway. Production requires
explicitly chosen hosting, authenticated transport, TLS, rate limiting,
bounded telemetry, permissions, observability and consent/revocation tests.
Do **not** expose the local unprotected gateway using a public listener.

Operator credentials are requested only during privileged actions and cleared
after use; never put them in the git repository, Pages HTML, browser storage,
query strings, analytics or telemetry records.

## HAARP subsystem

After the HAARP integration is merged, the Pages workflow can refresh bounded
HAARP source documents approximately every 15 minutes; scheduled GitHub Actions
are best effort. HAARP array capabilities are static published specifications:
180 elements, 12×15 grid, 3.6 MW design power. Current transmission state,
beam, frequency and per-antenna telemetry remain UNKNOWN/NOT PUBLIC.

## Rollback and launch completion

If the Pages deploy fails, review the specific failing step and roll back only
the offending commit or restore the previous verified revision. Do not remove
consent and provenance checks to force a launch.

**Launch status is successful only when the Pages deploy and an HTTPS browser
check are both verified.** Backend and device acceptance are separate gates.
