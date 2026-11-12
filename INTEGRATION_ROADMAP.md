# RuView + SkyNet integration roadmap

## Implemented in this archive

1. Authenticated read-only local RuView bridge: server health, mesh node count, last-frame availability and count of privacy-safe RuField events.
2. Public elevation query from USGS EPQS; LiDAR point-cloud **product discovery** through USGS TNM; Sentinel-1 radar **catalog discovery** through Copernicus OData.
3. NASA GIBS optical, land-surface-temperature, and cloud infrared map overlays; optional NASA FIRMS thermal anomalies.
4. Evidence states and SHA-256 of public response bytes; no RuView event/frame storage or remote device commands.
5. A map-first UI, protected loopback defaults, input validation and fifteen deterministic automated unit tests.
6. SkyNet v0.3 standalone HTML: user-submitted address geocoding, optional Google Maps JavaScript API (key required), keyless map fallback, NASA / USGS visual overlays, operator-supplied GeoJSON, synthetic demo markers clearly labeled, read-only evidence and session export.

## Not implemented: explicit blockers

- There is **no complete LiDAR cloud ingestion**: product discovery returns download links, not classified LAS/LAZ points. To add: PDAL/LAStools on sampled open LiDAR tiles; derive DEM/DSM/hillshade/slope; detection evaluation on annotated surface features.
- Sentinel-1 SAR is **metadata only**: no radar image downloading, SNAP/GDAL calibration, co-registration or InSAR deformation estimates. Repeat-pass interferometry needs suitable pairs, calibration and coherence checks.
- RuView integration has **no verified localization**: its CSI readings cannot be assigned to a global map coordinate without surveyed node location and calibration. Live Wi-Fi pose accuracy is not implied.
- No UWB/mmWave raw fusion within this gateway. RuView's own sensor fusion and point-cloud pipelines may be used separately after hardware-specific validation.
- Earth observation imagery has acquisition time, resolution and coverage limits. Global always-on thermal/wall/underground vision is not physically possible from these public layers.
- RuField signatures are **not verified**: a future verifier must bind trusted keys, signed payloads, timestamps, replay protection and version-specific canonical encodings.
- No automated alerts, AI-based anomaly claims, object identification, face/vital-sign tracking, historical Earth-change engine, geofencing, or secure cloud multi-user access.

## Suggested acceptance gates

A. **Contract gate:** pin a specific RuView commit/container digest and verify all four REST endpoints against that exact build, including token-auth and simulated mode.

B. **Hardware gate:** record exact ESP32/CSI/radar model, firmware baseline hash, consent/placement and time synchronization; acquire signed, raw local test vectors for presence/no-presence and calculate false-positive rate. Do not call an unverified CSI pose a detected human.

C. **Geospatial gate:** select one public, surveyed site with ground-truth mapping and download a licensed sample point cloud; hash raw bytes, convert to terrain raster, document grid CRS and cell size, evaluate known road/earthwork detections and false alarms.

D. **Fusion gate:** register camera/RF/LiDAR observations with separately checked coordinate frames and acquisition timestamps; reject association when locality, scale, accuracy or sensor provenance is unknown.

E. **Security and privacy gate:** require authenticated access, encrypt transport, restrict RF/vision to authorized areas, document retention and consent; disable sensitive monitoring by default; log public-source evidence and irreversible actions separately.

F. **Operations gate:** CI with deterministic fixtures, rate limiting, upstream failure tests, offline/missing-tile UI tests, monitoring and baseline rollback. All claims should carry VERIFIED/UNVERIFIED/BLOCKED/FAILED evidence states.
