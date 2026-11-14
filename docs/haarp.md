# SkyNet HAARP / SAGO observatory (read-only)

**Scope:** Public scientific metadata and endpoint reachability only. This is not a
live telemetry feed from the HAARP Ionospheric Research Instrument (IRI), nor
remote control of the transmitter or individual antenna elements.

## The array

The official University of Alaska Fairbanks HAARP FAQ describes an IRI phased
array of **180 crossed-dipole antennas** in a **12 × 15** layout across about
**33 acres**, with an upper design transmit-power capability of **3.6 MW**
and a selectable HF frequency range near **2.7–10 MHz**.

Source: https://haarp.gi.alaska.edu/faq

These are static specifications, not observed measurements. No public API has
been validated for current operating state, individual-element power/phase,
beam steering, live frequency, or array command/control. SkyNet shall mark
those values **UNKNOWN / NOT PUBLIC**, never derive them from a schedule.

## Public instruments

The HAARP diagnostic catalog publishes links for the ionosonde, oblique
ionosonde, fluxgate magnetometer, riometers, VLF receiver, induction
magnetometer, optical cameras, seismic station and other scientific equipment.

- https://haarp.gi.alaska.edu/diagnostic-suite
- https://ionograms.gi.alaska.edu/riometer/gakona/latest
- https://ionograms.gi.alaska.edu/ois/cathy_lane/cordova/latest
- https://www.gi.alaska.edu/monitors/magnetometer
- https://haarp.gi.alaska.edu/transmissions

The SAGO riometer site notes that instrument data quality is still being
evaluated. Link availability or presence of an image/chart must **not** be
presented as verified calibrated numeric observations, forecast skill,
transmission state, or discovery of a physical anomaly.

## Collection / deployment

Run:

```bash
python3 -m forecast.haarp
python3 -m unittest tests.test_haarp -v
```

The bounded collector uses GET to an approved set of HTTPS endpoints and
writes **data/public/haarp-status.json** plus
**data/public/haarp-source-status.json**. It records SHA-256 digests of
retrieved bodies but deliberately does not retain raw bodies or claim to
decode sensor plots. It does not access user networks or require credentials.
Each source receives VERIFIED for *endpoint/document validation only*,
BLOCKED for a measured retrieval failure, or UNVERIFIED for missing live
antenna telemetry. Sensor measurements always remain UNVERIFIED until
separate timestamped, licensed, parseable instrument feeds are integrated
and tested.

The Pages workflow requests a fresh bounded snapshot on each deployment and
is scheduled for a best-effort refresh every fifteen minutes. GitHub Actions
schedules can be delayed or skipped. The dashboard marks older than six
hours as stale. GitHub Pages remains static; the public site **does not**
become an always-on ingestion gateway.

**No false attribution:** Published transmission notices indicate announced
research activities, not proof of live transmission. Correlation with NOAA
or other datasets does not establish causation.

**Next validation gate:** Identify a published machine-readable instrument
feed with a documented timestamp, measurement units, calibration context,
usage rights, and reliable access. Add immutable fixture tests, stale-data
handling, and source-specific anomaly baselines before enabling any
quantitative alert. Keep transmission/array status UNKNOWN unless an
authorized first-party direct log or official operational telemetry proves it.
