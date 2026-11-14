# SkyNet CERN Intelligence Network

Scope: **public research metadata monitoring, not direct CERN sensor access**. The CERN module is a separate read-only collection feed for GitHub Pages and does not require CERN credentials.

## Sources and independent agents

| Agent | Public source | What can be verified | Explicit limitation |
| --- | --- | --- | --- |
| CERN.CMS | CERN Open Data experiment=CMS | Dataset search result metadata | Archived released records, not streaming collisions |
| CERN.ATLAS | CERN Open Data experiment=ATLAS | Dataset search result metadata | Same |
| CERN.ALICE | CERN Open Data experiment=ALICE | Dataset search result metadata | Same |
| CERN.LHCB | CERN Open Data experiment=LHCb | Dataset search result metadata | Same |
| CERN.CLOUD | CERN CLOUD experiment webpage | Research page retrieved | No CLOUD lab telemetry or cosmic-ray measurement |
| CERN.LHC_VISTAR | Public Vistar display directory | Public directory HTML retrieved | No image interpretation, numeric beam telemetry, or machine controls |

Sources:
- https://opendata.cern.ch/docs/about
- https://opendata.cern.ch/docs/cod-search-tips
- https://vistar-capture.s3.cern.ch/index.html
- https://home.cern/science/experiments/cloud/

## Collector

Run from the repository root:

```bash
python3 -m forecast.cern --allow-blocked
python3 -m unittest tests.test_cern -v
```

Output: `data/public/cern-status.json`. Six agents issue separate bounded HTTPS requests with a 9-second timeout each, 800 KiB maximum body size, same-host HTTPS redirects, fixed URLs, and schema validation. Only small released-record metadata and SHA-256 response digests are retained. Upstream errors become `BLOCKED`; they are not presented as positive evidence. Default CLI exits nonzero if any source blocks; `--allow-blocked` allows degraded GitHub Pages deployment with explicit fail-closed statuses.

The Pages workflow runs the collector before publishing `data/`; it checks tests before network collection. Scheduled runs depend on GitHub Actions and are best-effort, not guaranteed realtime.

## Status meaning

- `VERIFIED`: Source returned bounded, schema-validated public metadata on the recorded collection run. **Not** an independently verified scientific measurement.
- `UNVERIFIED`: Physical measurement, interpretation, and real detector access remain unverified. A retrieved page cannot justify a detector reading.
- `BLOCKED`: Endpoint fetch or validation failed, snapshot missing/stale, or correlation lacks comparable measurements.
- `FAILED`: Reserved for a measured negative acceptance test; normal unreachable sources do not imply a detector failure.

Browser freshness cutoff is 90 minutes since snapshot generation. A stale snapshot loses effective green source status even if it was once retrieved successfully. Historical record publication dates are not used to claim live sensing.

## Security and science boundaries

- Read-only public URLs, no internal CERN endpoint probing, control systems or credential scraping.
- URL redirects restricted to the expected hostname; content is bounded; no private IPs, secrets or user-supplied fetch targets.
- No mirroring of ROOT/large experimental files; only record titles, IDs, links and search totals.
- Per-agent SHA-256 public response digests and hash-linked collection events; hashes prove reproducible content equality only if the source bytes are separately retained.
- No optical parsing of Vistar screens. No direct radiation, particle-event, beam, CLOUD, sensor-antenna or accelerator control feed.
- CERN metadata is **not** training data. Cross-domain atmospheric/solar correlation stays **BLOCKED** pending calibrated observations, time alignment, rights checks, evaluation and approval.

SkyNet original integration is attributed to Matthew Blake Ward / 918 Technologies. CERN owns its research data and trademarks; follow source-specific use and citation requirements.
