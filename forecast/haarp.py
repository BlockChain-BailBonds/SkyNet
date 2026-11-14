"""Read-only HAARP observatory metadata adapter.

Retrieves public source documents and bounded endpoint bytes. It intentionally
does not infer live IRI transmitter state, per-antenna telemetry, power, beam
direction, physical anomalies, or quantitative measurements from HTML/images.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

DIAGNOSTICS_URL = "https://haarp.gi.alaska.edu/diagnostic-suite"
TRANSMISSIONS_URL = "https://haarp.gi.alaska.edu/transmissions"
RIOMETER_URL = "https://ionograms.gi.alaska.edu/riometer/gakona/latest"
OBLIQUE_URL = "https://ionograms.gi.alaska.edu/ois/cathy_lane/cordova/latest"
FAQ_URL = "https://haarp.gi.alaska.edu/faq"
FDSN_STATION_URL = ("https://data.raspberryshake.org/fdsnws/station/1/query?"
                    "network=AM&station=RFE1B&level=channel&format=text&nodata=404")
MAX_BYTES = 1_000_000
_ALLOWED_HOSTS = frozenset({"haarp.gi.alaska.edu", "ionograms.gi.alaska.edu"})
_NOTICE_HOSTS = frozenset({"drive.google.com", "haarp.gi.alaska.edu"})

SENSOR_LINKS = (
    ("Ionosonde", "https://giro.uml.edu/", "archive"),
    ("Oblique ionosonde", OBLIQUE_URL, "snapshot"),
    ("Fluxgate magnetometer", "https://www.gi.alaska.edu/monitors/magnetometer", "visualization"),
    ("SAGO riometer", RIOMETER_URL, "snapshot"),
    ("Nagoya riometer", DIAGNOSTICS_URL, "catalog"),
    ("VLF receiver", DIAGNOSTICS_URL, "catalog"),
    ("Induction magnetometer", DIAGNOSTICS_URL, "catalog"),
    ("All-sky cameras", DIAGNOSTICS_URL, "catalog"),
    ("Seismic / infrasound station RFE1B", FDSN_STATION_URL, "FDSN channel metadata"),
)


def _stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_public(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError("endpoint is not on the approved HAARP source allowlist")
    request = Request(url, headers={
        "User-Agent": "SkyNet-918-ReadOnly-HAARP/1.0 (public scientific research)",
        "Accept": "text/html, image/png, image/jpeg",
    })
    with urlopen(request, timeout=15) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in _ALLOWED_HOSTS:
            raise ValueError("unapproved redirect")
        body = response.read(MAX_BYTES + 1)
        if not body or len(body) > MAX_BYTES:
            raise ValueError("empty or oversized HAARP response")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        if content_type not in {"text/html", "image/png", "image/jpeg"}:
            raise ValueError("unexpected HAARP content type")
        if content_type == "image/png" and not body.startswith(bytes((137,80,78,71,13,10,26,10))):
            raise ValueError("invalid PNG")
        if content_type == "image/jpeg" and not body.startswith(bytes((255,216))):
            raise ValueError("invalid JPEG")
        return body


def fetch_fdsn_metadata(url=FDSN_STATION_URL):
    """Retrieve bounded station metadata only; no waveform redistribution."""
    parsed = urlparse(url)
    if url != FDSN_STATION_URL or parsed.scheme != "https" or parsed.hostname != "data.raspberryshake.org":
        raise ValueError("endpoint is not the approved RFE1B FDSN station query")
    request = Request(url, headers={
        "User-Agent": "SkyNet-918-HAARP-StationMetadata/1.0",
        "Accept": "text/plain",
    })
    with urlopen(request, timeout=15) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "data.raspberryshake.org":
            raise ValueError("unapproved FDSN redirect")
        if response.headers.get("Content-Type", "").split(";")[0].lower() != "text/plain":
            raise ValueError("unexpected FDSN metadata content type")
        body = response.read(65_537)
    if not body or len(body) > 65_536:
        raise ValueError("empty or oversized FDSN station metadata")
    return body


def normalize_fdsn_channels(body):
    try:
        lines = [line for line in body.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError as exc:
        raise ValueError("FDSN metadata is not UTF-8") from exc
    if len(lines) < 2:
        raise ValueError("FDSN station metadata missing")
    header = lines[0].lstrip("#").split("|")
    required = {"Network", "Station", "Location", "Channel", "Latitude", "Longitude",
                "Elevation", "SensorDescription", "ScaleUnits", "SampleRate", "StartTime", "EndTime"}
    if not required.issubset(header):
        raise ValueError("FDSN channel schema mismatch")
    candidates = []
    for line in lines[1:]:
        values = line.split("|")
        if len(values) != len(header):
            raise ValueError("FDSN channel column mismatch")
        row = dict(zip(header, values))
        if row["Network"] != "AM" or row["Station"] != "RFE1B" or row["Channel"] not in {"EHZ", "HDF"}:
            raise ValueError("unexpected FDSN station or channel")
        try:
            lat, lon = float(row["Latitude"]), float(row["Longitude"])
            elevation, sample_rate = float(row["Elevation"]), float(row["SampleRate"])
            datetime.fromisoformat(row["StartTime"].replace("Z", "+00:00"))
            if row["EndTime"]:
                datetime.fromisoformat(row["EndTime"].replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid FDSN numeric or timestamp metadata") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 < sample_rate <= 10000):
            raise ValueError("FDSN metadata outside bounds")
        candidates.append({"network":"AM","station":"RFE1B","location":row["Location"],
            "channel":row["Channel"],"sensor_description":row["SensorDescription"][:80],
            "scale_units":row["ScaleUnits"][:20],"sample_rate_hz":sample_rate,
            "geometry":{"type":"Point","coordinates":[lon,lat]},"elevation_m":elevation,
            "start_time":row["StartTime"],"end_time":row["EndTime"] or None,
            "open_channel":not bool(row["EndTime"]),"waveform_measurement_status":"UNVERIFIED_NOT_RETRIEVED"})
    # Prefer the currently open epoch for each of the two channels.
    output=[]
    for channel in ("EHZ","HDF"):
        rows=[row for row in candidates if row["channel"]==channel]
        if not rows: raise ValueError("required FDSN channel missing")
        output.append(next((row for row in rows if row["open_channel"]),rows[-1]))
    return output


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_href is not None:
            self.links.append((" ".join(" ".join(self.current_text).split()), self.current_href))
            self.current_href = None
            self.current_text = []


def _notices(html):
    parser = _Links()
    parser.feed(html)
    links = []
    for title, href in parser.links:
        target = urljoin(TRANSMISSIONS_URL, href)
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.hostname not in _NOTICE_HOSTS or not title:
            continue
        if "20" not in title:
            continue
        links.append({"title": title[:120], "url": target})
    return links[:24]


def collect(fetch=fetch_public, checked_at=None, fdsn_fetch=None):
    """Return a document snapshot and source statuses; no command/control access."""
    at = checked_at or _stamp()
    record = {
        "schema_version": "1.0",
        "retrieved_at": at,
        "evidence_scope": "public document/endpoint availability only; not live sensor calibration",
        "iri_antenna_array": {
            "name": "Ionospheric Research Instrument",
            "element_count": 180,
            "layout": [12, 15],
            "site_acres": 33,
            "maximum_transmitter_power_mw": 3.6,
            "published_frequency_range_mhz": [2.7, 10.0],
            "specification_source": FAQ_URL,
            "actual_transmission_state": "UNKNOWN",
            "current_frequency_mhz": None,
            "current_power_mw": None,
            "beam_direction": None,
            "individual_element_telemetry": "NOT_PUBLIC",
            "remote_control": "NOT_AVAILABLE",
            "last_transmission_notice": None,
            "transmission_notices": [],
        },
        "sensors": [
            {"name": name, "source_url": url, "access_kind": kind,
             "measurement_status": "UNVERIFIED", "measurement_time": None}
            for name, url, kind in SENSOR_LINKS
        ],
        "source_documents": {},
        "fdsn_station": None,
    }
    statuses = []

    def check(name, url, check_text=None):
        try:
            body = fetch(url)
            if not isinstance(body, bytes) or not body or len(body) > MAX_BYTES:
                raise ValueError("invalid bounded response")
            if check_text:
                decoded = body.decode("utf-8", errors="replace")
                if any(term not in decoded for term in check_text):
                    raise ValueError("official page structure not confirmed")
            digest = hashlib.sha256(body).hexdigest()
            record["source_documents"][name] = {
                "url": url, "sha256": digest, "bytes": len(body),
                "retrieved_at": at, "raw_body_retained": False,
            }
            statuses.append({"source": name, "status": "VERIFIED",
                             "detail": "Source response validated; measurement/antenna telemetry NOT verified",
                             "checked_at": at, "source_url": url, "sha256": digest})
            return body
        except (ValueError, OSError, UnicodeError, TimeoutError) as exc:
            statuses.append({"source": name, "status": "BLOCKED",
                             "detail": type(exc).__name__ + ": " + str(exc)[:140],
                             "checked_at": at, "source_url": url})
            return None

    diagnostics = check("HAARP diagnostic catalog", DIAGNOSTICS_URL, ("Ionosonde", "Riometer"))
    notices = check("HAARP transmission notices", TRANSMISSIONS_URL, ("Transmission Notices",))
    if diagnostics is None:
        for sensor in record["sensors"]:
            sensor["catalog_status"] = "BLOCKED"
    else:
        for sensor in record["sensors"]:
            sensor["catalog_status"] = "VERIFIED"
    if notices is not None:
        parsed = _notices(notices.decode("utf-8", errors="replace"))
        record["iri_antenna_array"]["transmission_notices"] = parsed
        if parsed:
            record["iri_antenna_array"]["last_transmission_notice"] = parsed[0]
    for label, url in (
        ("HAARP SAGO riometer chart", RIOMETER_URL),
        ("HAARP oblique ionosonde chart", OBLIQUE_URL),
    ):
        check(label, url)
    # FDSN station metadata validates that the linked HAARP RFE1B instrument
    # exposes EHZ seismic and HDF infrasound channels. It is not a waveform.
    if fdsn_fetch is None:
        fdsn_fetch = fetch_fdsn_metadata if fetch is fetch_public else None
    try:
        if fdsn_fetch is None:
            raise OSError("FDSN metadata fixture not supplied")
        body = fdsn_fetch(FDSN_STATION_URL)
        if not isinstance(body, bytes) or not body or len(body) > 65_536:
            raise ValueError("invalid bounded FDSN response")
        channels = normalize_fdsn_channels(body)
        digest = hashlib.sha256(body).hexdigest()
        record["source_documents"]["HAARP RFE1B FDSN channel metadata"] = {
            "url": FDSN_STATION_URL, "sha256": digest, "bytes": len(body),
            "retrieved_at": at, "raw_body_retained": False,
        }
        record["fdsn_station"] = {"network":"AM","station":"RFE1B","channels":channels,
            "metadata_status":"VERIFIED","waveform_data_published":False,
            "waveform_policy":"Not retrieved or redistributed; provider license and miniSEED analysis required",
            "source_url":FDSN_STATION_URL,"sha256":digest,"checked_at":at}
        sensor = next(s for s in record["sensors"] if "RFE1B" in s["name"])
        sensor.update({"catalog_status":"VERIFIED","measurement_status":"UNVERIFIED",
            "channels":[row["channel"] for row in channels],"channel_metadata_status":"VERIFIED"})
        statuses.append({"source":"HAARP RFE1B FDSN channel metadata","status":"VERIFIED",
            "detail":"EHZ seismic and HDF infrasound channels validated; waveforms not retrieved",
            "checked_at":at,"source_url":FDSN_STATION_URL,"sha256":digest})
    except (ValueError,OSError,UnicodeError,TimeoutError) as exc:
        statuses.append({"source":"HAARP RFE1B FDSN channel metadata","status":"BLOCKED",
            "detail":type(exc).__name__+": "+str(exc)[:140],"checked_at":at,"source_url":FDSN_STATION_URL})
    statuses.append({
        "source": "HAARP IRI array live state",
        "status": "UNVERIFIED",
        "detail": "Official specifications and notices only; no public element-level or live transmitter telemetry",
        "checked_at": at, "source_url": FAQ_URL,
    })
    return record, statuses

def main():
    """Refresh publishable read-only HAARP status; never label charts as decoded measurements."""
    import json
    from pathlib import Path
    record, statuses = collect()
    out = Path(__file__).resolve().parents[1] / "data" / "public"
    out.mkdir(parents=True, exist_ok=True)
    (out / "haarp-status.json").write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    (out / "haarp-source-status.json").write_text(
        json.dumps(statuses, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
