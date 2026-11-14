# Live source audit

## FireWatch replacement

NASA FIRMS remains an optional credentialed thermal-anomaly source, but it is no longer the required FireWatch path. The deployed collector uses the National Interagency Fire Center WFIGS current-incident service, filters explicitly for `IncidentTypeCategory = WF`, and publishes operational wildfire incident points. Prescribed fires are rejected. WFIGS records are not described as satellite detections or automatic local danger determinations.

## CERN

The live audit retrieved five of six bounded public endpoints. CMS, ATLAS, LHCb catalogs, the CLOUD research page, and the public LHC display directory passed. The ALICE catalog response exceeded the collector's 800 KB safety limit and was rejected rather than truncated or mislabeled. CERN currently provides preserved open datasets and metadata through this integration—not a supported live detector or environmental sensor stream. Reported state: zero live detector streams and zero directly ingested numeric physics observations.

ALICE publishes genuine collision datasets, including reconstructed event data, but those large ROOT/ESD datasets require experiment-specific analysis and are not appropriate as real-time environmental sensors. Adding an offline CERN analysis pipeline would be a separate data-science subsystem with dataset DOI/version pinning, storage controls, and physics-specific validation.

## HAARP

The live audit validated the official diagnostic catalog, transmission-notice page, SAGO riometer chart response, and oblique-ionosonde chart response. These are reachable documents/images. They do not expose machine-readable numeric samples, acquisition timestamps, current transmitter state, array-element telemetry, power, frequency, or beam direction through the checked public interfaces. The nine cataloged instruments therefore remain `UNVERIFIED` measurements, with IRI live state `UNKNOWN`.

Promoting HAARP instruments to verified numeric sensors requires an official machine-readable endpoint containing values, units, calibration/provenance, and acquisition timestamps. Image/chart interpretation is intentionally not used as a substitute.

The HAARP diagnostic page also links station `AM.RFE1B.00`, for which Raspberry Shake publishes standards-based FDSN station metadata. SkyNet now validates the open `EHZ` vertical-seismic velocity and `HDF` infrasound/atmospheric-pressure channels, including coordinates, elevation, scale units, sample rate, and channel epoch. This fixes the missing machine-readable instrument identity, but does not claim waveform measurements: miniSEED data is not retrieved, decoded, stored, or redistributed by the Pages pipeline.
