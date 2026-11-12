# SkyNet × RuView — Read-only sensing dashboard

**Intellectual property by Matthew Blake Ward, in association with 918 Technologies.**

A **local-first, read-only integration starter**, not a validated sensing product. SkyNet is the project name for the integration; RuView, government datasets, map layers and external service APIs retain their respective ownership and terms. See `IP_NOTICE.md` and `THIRD_PARTY_NOTICES.md`.

## Start

Requires Python 3.10+ (no packages), a web browser, and internet for public layers. It runs on Linux, Windows, macOS, x86 or ARM64 including Jetson (provided Python is available).

```bash
cd 918_skynet_ruview
python3 server.py
```

Open **http://127.0.0.1:8787**.

RuView defaults to `http://127.0.0.1:3000`. If your RuView server requires API bearer-token authentication, supply the same token **only to this backend** using `RUVIEW_API_TOKEN`:

```bash
read -rsp "RuView API token: " RUVIEW_API_TOKEN; echo
export RUVIEW_API_TOKEN
python3 server.py
```

If RuView runs elsewhere on your trusted LAN:

```bash
RUVIEW_URL=http://192.168.1.25:3000 RUVIEW_ALLOW_LAN=1 python3 server.py
```

**Do not expose the unprotected gateway or RuView server to the public internet.** `SKYNET_ALLOW_REMOTE=1` disables only SkyNet's listener safeguard; it does not add authentication, access controls or encryption.

Optional NASA FIRMS fire detections, with a free registration-issued MAP_KEY:

```bash
read -rsp "NASA FIRMS MAP_KEY: " FIRMS_MAP_KEY; echo
export FIRMS_MAP_KEY
python3 server.py
```

Do not put keys in the browser or commit them to Git.

## Connected adapters and exact limits

| Data | Access | Information exposed | Limit |
| --- | --- | --- | --- |
| RuView `/health` | Local HTTP | Self-reported source/server state | Simulation is not actual hardware acceptance |
| RuView `/api/v1/mesh` | Local HTTP | Node count | No MAC addresses or location data exported |
| RuView `/api/field` | Local HTTP | Count of egress-safe signed-field events, signing-key flag | Gateway **does not verify digital signatures** |
| RuView `/api/v1/sensing/latest` | Local HTTP | Frame availability, key presence | No raw CSI/vital signs/pose persisted |
| USGS EPQS | Open HTTPS | Point elevation, meters | DEM point sample, **not** feature classification |
| USGS TNM Access | Open HTTPS | LiDAR point-cloud product search metadata | Product list only, raw LAZ not analyzed |
| Copernicus Data Space OData | Open HTTPS catalog | Five latest Sentinel-1 catalog records within 45 days | Radar **metadata**, no downloaded GRD/SAR processing |
| NASA GIBS WMS | Public raster tiles | Daytime optical, MODIS surface-temperature, GOES cloud infrared | Date/layer-dependent tiles; no individual object detection |
| NASA FIRMS area API | Optional MAP_KEY | Up to 100 thermal anomaly spots in selected area | No guarantee of a confirmed fire; 1-day window |

The local RuView measurements and regional Earth layers appear side-by-side **without implying that they observe the same geographic location**. Avoid misleading fusion of incompatible scales, modalities and timestamps.

## Evidence semantics

- `VERIFIED` = remote endpoint returned parseable data **only**; source measurement itself and feature interpretation remain unverified.
- `UNVERIFIED` = self-reported sensing result, unresolved provenance, or no physical evidence.
- `SIMULATED` = RuView reports simulated source.
- `BLOCKED` = no access, missing key, timeout, or invalid upstream output.
- `FAILED` is reserved for a measured acceptance failure; this dashboard never manufactures one.

A SHA-256 of each successfully retrieved public response body is recorded in `data/public_evidence.jsonl`. Failed requests have no body hash. Raw data payloads are **not** stored, so a hash on its own cannot reproduce or revalidate the source bytes. For a reproducible scientific pipeline, retain licensed public raw data, metadata, acquisition geometry, calibration and tests in a separate controlled store.

No model-derived conclusion, vital-sign diagnosis, person identification, private-area targeting, physical hardware acceptance, LoRA training, deployment, or flash command is implemented.

## API

- `GET /api/health`
- `GET /api/config`
- `GET /api/ruview`
- `GET /api/scan?lat=39&lon=-98&radius_km=5`
- `GET /api/evidence`

Only enrollment POST routes are supported; all other write routes are rejected. Source API URL targets are fixed in the backend. RuView host must be a literal loopback IP or private LAN IP with explicit opt-in.

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Before production deployment

Add authenticated users, CSRF controls if writing endpoints ever exist, HTTPS and rate limits; pin dependency and source versions; isolate the sensor network; implement RuField signature validation against an explicitly trusted key; validate real CSI hardware/calibration and geographic source acquisition evidence; retain source body only with appropriate privacy and data-rights controls; add indexed time-series and measured multi-modal associations. No public deployment or real hardware testing was performed when this starter was authored.

## Attribution and rights

SkyNet original integration code, dashboard composition, original documentation, and related newly authored project materials: **© 2026 Matthew Blake Ward, in association with 918 Technologies. All rights reserved.** This statement does not claim ownership of RuView or third-party imagery, data, services, or libraries. No permission or commercial redistribution license is granted by this package for third-party material. Before redistribution, review applicable third-party licenses and any brand/trademark conflicts, including the name “SkyNet”.

See `IP_NOTICE.md` and `THIRD_PARTY_NOTICES.md` for scope and provenance.

## Source documentation

- https://github.com/ruvnet/RuView/blob/main/docs/user-guide.md
- https://tnmaccess.nationalmap.gov/api/v1/docs
- https://epqs.nationalmap.gov/
- https://documentation.dataspace.copernicus.eu/APIs/OData.html
- https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi
- https://firms.modaps.eosdis.nasa.gov/api/area

## SkyNet v0.3 map/dashboard upgrade

**Interactive web interface:** `static/index.html`. **Standalone copy:** `SkyNet_918_Interactive_Google_Maps.html`. Both include address lookup, coordinate targeting, in-map Google Maps JavaScript mode (with user-supplied restricted key), keyless OpenStreetMap basemap, source imagery overlays, RuView summary, local GeoJSON import, explicit demo geometry, and JSON session export.

For detailed setup and measurement caveats, see **`WEB_MAP_GUIDE.md`**. The HTML still needs internet for tiles, geocoding and external imagery. Data retrieval through the read-only gateway requires running `python3 server.py` rather than merely opening the standalone file.

The public Photon instance is used only for a manually submitted address/place lookup (no autocomplete, bulk lookups or automatic scanning). Larger deployments must use a self-hosted or contracted geocoding service. A Google Maps URL button works without a key, while rendering Google Maps *inside the page* requires Google's JavaScript API key.

## SkyNet v0.5: text-message invitations and opt-in motion sensors

The operator dashboard now has an **SMS sensor invitations** panel; `static/join.html` is the mobile consent page, and `optin.py` implements time-limited, single-use tokens and ephemeral in-memory sensor sessions. This is a self-reported voluntary **phone-motion** sensor, not RuView Wi-Fi CSI and not independent proof of physical location. The SMS button opens the device's messaging app for manual sending; the gateway does not send SMS. A public HTTPS reverse proxy is required to serve the mobile enrollment page.

Run with `SKYNET_ADMIN_TOKEN` and `SKYNET_PUBLIC_URL` set to your private operator secret and real HTTPS hostname respectively. See **`SMS_ENROLLMENT_GUIDE.md`** for secure proxy configuration, consent handling, limitations and test instructions. Keep the RuView and operator APIs private.

New API routes: `POST /api/sites/invite` (operator authorized), `GET /api/sites/status` and `GET /api/sites/ruview` (operator authorized), `GET /api/enroll/info` (one-time invite), `POST /api/enroll/start`, `POST /api/enroll/sample`, `POST /api/enroll/stop`. Invitations and session state are RAM-only and lost on restart. The server does not store phone numbers or sent-message records.
