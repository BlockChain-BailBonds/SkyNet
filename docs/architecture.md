# SPIN MVP architecture

SkyNet Main is a static, single-entry GitHub Pages application. It reads bounded public JSON snapshots and remains usable when the optional browser LLM is unavailable. Scheduled Actions fetch official feeds, normalize strict schemas, apply deterministic alert rules, test, and publish. The local Python gateway remains the only supported RuView and consent-enrollment backend.

`official sources → validation/provenance → deterministic fusion → alert classification → public snapshots → Main/Pocket`

The LLM may summarize only allowlisted snapshot data; it cannot fetch arbitrary URLs, modify GitHub, or create official warnings. Pages cannot accept telemetry. Authenticated autonomous device uplink is **BLOCKED** pending a trusted HTTPS gateway.

## Real environmental instrumentation

`forecast/environmental_sensors.py` retrieves credential-free observations from three independent official networks: USGS instantaneous stream gauges, NOAA CO-OPS tide stations, and NOAA NDBC ocean buoys. Each adapter allowlists its HTTPS host, caps payload size, validates timestamps and finite numeric values, preserves units/station coordinates, records a SHA-256 payload digest, and isolates failures per station. These are measurements—not automatic flood, storm, or safety classifications.
