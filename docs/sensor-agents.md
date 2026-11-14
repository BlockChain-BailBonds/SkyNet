# SkyNet Per-Sensor Intelligence Agents — launch implementation

**Scope:** Each physical instrument or bounded public data feed owns an independent
sensor agent, observation evidence, learning eligibility, and immutable
training-candidate lineage. The supervisory agent watches the ingestion and
outbound normalized result of every supported connector. It is not allowed to
exfiltrate credentials or capture private data solely because it can observe it.

## Implemented agent IDs

| Agent | Source | Learning mode now |
|---|---|---|
| `NOAA.GRS` | NOAA current geomagnetic/radio/radiation scales | Evidence monitored; categorical current state, no learned numeric model |
| `NOAA.KP` | NOAA 3-hour observed planetary Kp | Shadow robust median/MAD training on timestamped, bounded numeric history |
| `NOAA.GOES_FLARES` | GOES latest flare event | Evidence monitored; a single recent event is insufficient for reliable training |
| `NOAA.BULLETINS` | NOAA alert/warning bulletin history | Evidence monitored; bulletins not automatically treated as active alerts |
| `HAARP.IRI_ARRAY` | Official array notices and specifications | Metadata only; **no remote control** or public element-level telemetry |
| `HAARP.IONOSONDE` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |
| `HAARP.RIOMETER` | Official SAGO riometer chart | Metadata only, awaiting numerical authorized samples |
| `HAARP.OBLIQUE_IONOSONDE` | Official oblique ionosonde chart | Metadata only, awaiting numerical authorized samples |
| `HAARP.FLUXGATE` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |
| `HAARP.VLF` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |
| `HAARP.INDUCTION_MAGNETOMETER` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |
| `HAARP.ALL_SKY_CAMERA` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |
| `HAARP.SEISMIC` | Official diagnostics catalog | Metadata only, awaiting numerical authorized samples |

Every sensor appears in `data/public/sensor-agents.json` with its own status,
training disposition, and incoming, outgoing, or linked metadata event counts.
This is **13 agents**, not 13 trained or independently validated instruments.

## Two learning stages, never confused

1. **Observe/monitor:** Allowlisted public HTTPS JSON requests are bounded and
   parsed. Ingress hashes, normalized egress hashes, acquisition timestamps and
   quality decisions are recorded as a SHA-256 hash chain. Hashing does not
   encrypt data and does not by itself verify that the upstream provider is
   correct; TLS plus schema, timestamp and calibration checks remain necessary.
2. **Shadow train:** For sources with enough *legitimate numeric time-series*
   observations, compute descriptive baseline parameters over a chronological
   training partition, evaluate on a later holdout, and emit a versioned,
   unapproved candidate. The only enabled initial candidate is planetary Kp.
   The Kp baseline is **not a predictive solar-weather model** and is never
   used to generate emergency alerts.

**No unsupervised promotion:** Changes to baseline thresholds, model weights,
agent code, and production alert rules require approval, versioned artifacts,
reproducible tests, a real event backtest, and a rollback target. No trainable
weights are shipped or falsely advertised for HAARP sources without numeric
observations.

## Data rights and privacy

Production sensor adapters must declare source/license, consent where relevant,
schema, units, calibration, acquisition timestamp, location uncertainty, age
threshold, provenance hash, and retention. No private CSI, camera images,
microphone audio, owner location, access token, or raw private payload may be
copied into public GitHub Pages, a CI log, or a public training artifact.
Do not treat all ingressed data, agent outputs, or generated text as reliable
ground truth; that creates feedback loops, poisoning and model drift.
Public snapshots include only source digests, bounded summaries, and shadow
baseline statistics.

## Command line

Run a single NOAA collection:
```bash
python3 -m forecast.space_weather
python3 -m sensor_agents.report
```

Run a **local process** that refreshes NOAA observations every five minutes:
```bash
python3 -m forecast.space_weather --watch --interval 300
```

The local watch runs only while the process is running and does not emit a live
websocket by itself. Use the separate protected gateway for authenticated
device telemetry.

For unattended collection **without GitHub Pages**, GitHub Actions workflow
`.github/workflows/solar-watch.yml` runs on a best-effort 15-minute schedule
and uploads a seven-day evidence artifact. Use
`workflow_dispatch` for an on-demand run after merge. GitHub may delay or
skip scheduled workflows. To deploy the public dashboard, a repository
administrator must enable **Settings → Pages → Source: GitHub Actions**
and verify the deploy job. A working dashboard does not prove the private
gateway or any ESP32 hardware has connected.

## Required next stage

The next implementable training improvements require historical labeled
observations and an evaluation suite: robust Kp forecasting baselines,
flare-event classification and severity, model selection by rolling-window
backtests, concept drift detection, metric slices by activity regime,
quality-gated candidate promotion, and red/blue testing for source
corruption and spoofing. A cloud database or operator-controlled local archive
will be required for persistent private device observations and checkpoint
history; temporary Actions artifacts are not that archive.
