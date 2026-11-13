# Baseline and validation evidence

Starting commit: `5637fb25a5464c149d6b91ad0676363a3a2c7465`.

## Baseline

- **VERIFIED:** 26 existing unit/HTTP tests; read-only gateway validation; privacy-safe RuView summaries; public map layers; restricted user-supplied Google key flow; manual SMS invitation and explicit consent/revoke routes.
- **UNVERIFIED:** real RuView hardware, remote reverse proxy, public deployment behavior, physical sensor calibration.
- **BLOCKED:** browser model weight test, ESP32 hardware acceptance, NASA FIRMS without credential, authenticated autonomous Pocket uploads, guaranteed real-time delivery.

## Evidence rules

`VERIFIED`, `UNVERIFIED`, `SIMULATED`, `BLOCKED`, and `FAILED` describe operational evidence. Hazard records separately use `OFFICIAL_FORECAST`, `OFFICIAL_WARNING`, `OBSERVED_EVENT`, `MODEL_RISK`, `EXPERIMENTAL_ANOMALY`, or `SIMULATED`. Missing data never implies safety. An LLM explanation is never a calibrated probability.
