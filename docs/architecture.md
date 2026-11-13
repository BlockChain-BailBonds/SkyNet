# SPIN MVP architecture

SkyNet Main is a static, single-entry GitHub Pages application. It reads bounded public JSON snapshots and remains usable when the optional browser LLM is unavailable. Scheduled Actions fetch official feeds, normalize strict schemas, apply deterministic alert rules, test, and publish. The local Python gateway remains the only supported RuView and consent-enrollment backend.

`official sources → validation/provenance → deterministic fusion → alert classification → public snapshots → Main/Pocket`

The LLM may summarize only allowlisted snapshot data; it cannot fetch arbitrary URLs, modify GitHub, or create official warnings. Pages cannot accept telemetry. Authenticated autonomous device uplink is **BLOCKED** pending a trusted HTTPS gateway.
