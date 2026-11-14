"""SkyNet NOAA SWPC Solar Watch: bounded, evidence-gated read-only ingestion.

NOAA observations are not predictions of a guaranteed outage or solar event.
GitHub Pages is static; use --watch locally for a five-minute refresh loop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from sensor_agents.runtime import NOAA_SPECS, Supervisor

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "public" / "space-weather.json"
BASE = "https://services.swpc.noaa.gov"
ENDPOINTS = {
    "scales": "/products/noaa-scales.json",
    "kp": "/products/noaa-planetary-k-index.json",
    "flare": "/json/goes/primary/xray-flares-latest.json",
    "bulletins": "/products/alerts.json",
}
MAX_BYTES = 1_000_000
MAX_CLOCK_SKEW = timedelta(minutes=6)
FRESHNESS = {"scales": timedelta(minutes=45), "kp": timedelta(hours=5),
             "flare": timedelta(days=7), "bulletins": timedelta(days=31)}
FLARE_PATTERN = re.compile(r"^[ABCMX][0-9]{1,3}(?:[.][0-9]{1,2})?$")


class SourceError(ValueError):
    """The remote source cannot be admitted to the monitored data model."""


def utc(value):
    if not isinstance(value, str) or not value.strip():
        raise SourceError("missing UTC timestamp")
    try:
        item = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceError("invalid UTC timestamp") from exc
    if item.tzinfo is None:
        # SWPC Kp and issue_datetime use UTC without a suffix.
        item = item.replace(tzinfo=timezone.utc)
    return item.astimezone(timezone.utc)


def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def bounded_fetch(url):
    if url not in {BASE + path for path in ENDPOINTS.values()}:
        raise SourceError("unapproved NOAA endpoint")
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "SkyNet-918-SolarWatch/1.0 (read-only research monitor)",
    })
    with urlopen(req, timeout=15) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != "services.swpc.noaa.gov":
            raise SourceError("redirect outside NOAA allowlist")
        data = response.read(MAX_BYTES + 1)
        if len(data) == 0 or len(data) > MAX_BYTES:
            raise SourceError("empty or oversized NOAA response")
        return data


def valid_age(timestamp, now, max_age):
    age = now - timestamp
    return -MAX_CLOCK_SKEW <= age <= max_age


def normalize_scales(payload, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("0"), dict):
        raise SourceError("NOAA scales schema mismatch")
    current = payload["0"]
    at = utc(str(current.get("DateStamp", "")) + "T" + str(current.get("TimeStamp", "")) + "Z")
    values = {}
    for key in ("G", "R", "S"):
        section = current.get(key)
        if not isinstance(section, dict) or not str(section.get("Scale", "")).isdigit():
            raise SourceError("missing NOAA current scale " + key)
        number = int(section["Scale"])
        if number < 0 or number > 5:
            raise SourceError("NOAA current scale outside 0..5")
        values[key] = number
    return {"observed_at": stamp(at), "levels": values,
            "fresh": valid_age(at, now, FRESHNESS["scales"]),
            "meaning": "NOAA currently published G/R/S scales; not a forecast"}


def normalize_kp(payload, now):
    if not isinstance(payload, list) or not payload:
        raise SourceError("missing NOAA Kp observations")
    candidates = []
    for row in payload:
        if not isinstance(row, dict):
            raise SourceError("invalid NOAA Kp row")
        at = utc(row.get("time_tag"))
        value = row.get("Kp")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SourceError("invalid NOAA Kp value")
        number = float(value)
        if not math.isfinite(number) or not 0 <= number <= 9:
            raise SourceError("Kp outside 0..9")
        if at <= now + MAX_CLOCK_SKEW:
            candidates.append((at, number))
    if not candidates:
        raise SourceError("no Kp observations at or before retrieval")
    at, value = max(candidates, key=lambda item: item[0])
    return {"observed_at": stamp(at), "value": value,
            "fresh": valid_age(at, now, FRESHNESS["kp"]),
            "meaning": "Observed three-hour planetary Kp index (not a future prediction)"}


def normalize_flare(payload, now):
    if not isinstance(payload, list):
        raise SourceError("GOES flare source is not a list")
    rows = []
    for event in payload:
        if not isinstance(event, dict):
            raise SourceError("invalid GOES flare entry")
        if not event.get("max_class"):
            continue
        flare_class = str(event["max_class"])
        if not FLARE_PATTERN.fullmatch(flare_class):
            raise SourceError("unrecognized GOES flare class")
        at = utc(event.get("max_time") or event.get("begin_time"))
        if at > now + MAX_CLOCK_SKEW:
            raise SourceError("future-dated flare")
        rows.append({"peak_at": stamp(at), "peak_class": flare_class,
                     "satellite": str(event.get("satellite", "unknown"))[:20],
                     "age_minutes": max(0, int((now - at).total_seconds() // 60))})
    latest = max(rows, key=lambda e: e["peak_at"]) if rows else None
    return {"latest": latest, "observed_at": latest["peak_at"] if latest else None,
            "fresh": latest is not None and valid_age(utc(latest["peak_at"]), now, FRESHNESS["flare"]),
            "meaning": "Latest reported GOES flare peak; historical event, NOT proof of an ongoing flare"}


def normalize_bulletins(payload, now):
    if not isinstance(payload, list):
        raise SourceError("NOAA bulletins source is not a list")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            raise SourceError("malformed bulletin")
        at = utc(item.get("issue_datetime"))
        if at > now + MAX_CLOCK_SKEW:
            raise SourceError("future-dated NOAA bulletin")
        message = item.get("message")
        if not isinstance(message, str):
            raise SourceError("invalid NOAA bulletin message")
        first = next((line.strip() for line in message.splitlines()
                      if re.match(r"^(?:CONTINUED ALERT|ALERT|WATCH|WARNING|EXTENDED WARNING):", line.strip())), "")
        if not first:
            first = next((line.strip() for line in message.splitlines() if line.strip()), "Untitled NOAA bulletin")
        rows.append({"issued_at": stamp(at), "product_id": str(item.get("product_id", ""))[:25],
                     "headline": first[:180],
                     "is_recent": valid_age(at, now, timedelta(hours=24))})
    rows.sort(key=lambda row: row["issued_at"], reverse=True)
    return {"recent": rows[:8], "observed_at": rows[0]["issued_at"] if rows else None,
            "fresh": bool(rows) and valid_age(utc(rows[0]["issued_at"]), now, FRESHNESS["bulletins"]),
            "meaning": "Recent issue-history; bulletin publication alone does not prove an alert remains active"}


NORMALIZERS = {
    "scales": normalize_scales, "kp": normalize_kp,
    "flare": normalize_flare, "bulletins": normalize_bulletins,
}


def collect(fetch=bounded_fetch, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SourceError("collector clock must include timezone")
    now = now.astimezone(timezone.utc)
    observed = {}
    sources = []
    supervisor = Supervisor(NOAA_SPECS, stamp(now))
    agent_ids = {"scales": "NOAA.GRS", "kp": "NOAA.KP", "flare": "NOAA.GOES_FLARES", "bulletins": "NOAA.BULLETINS"}
    for name, path in ENDPOINTS.items():
        url = BASE + path
        try:
            raw = fetch(url)
            if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
                raise SourceError("invalid or unbounded response")
            supervisor.ingress(agent_ids[name], raw)
            document = json.loads(raw)
            value = NORMALIZERS[name](document, now)
            supervisor.egress(agent_ids[name], value)
            if name == "kp":
                supervisor.candidate(agent_ids[name], [
                    {"observed_at": stamp(utc(row["time_tag"])), "value": row["Kp"]}
                    for row in document
                ])
            observed[name] = value
            sources.append({"source": name, "source_url": url, "status":
                            "VERIFIED" if value["fresh"] else "UNVERIFIED",
                            "observed_at": value["observed_at"],
                            "checked_at": stamp(now),
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "detail": "Schema parsed; source timestamp within defined freshness window"
                            if value["fresh"] else "No sufficiently recent source event; historical only"})
        except (SourceError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            supervisor.quarantine(agent_ids[name], "SCHEMA_REJECTED" if isinstance(exc, (SourceError, json.JSONDecodeError)) else "FETCH_FAILED")
            sources.append({"source": name, "source_url": url, "status": "BLOCKED",
                            "checked_at": stamp(now),
                            "detail": type(exc).__name__ + ": " + str(exc)[:125]})
    # A valid current scales record is the only gate for current reported NOAA G/R/S levels.
    scales_current = "scales" in observed and observed["scales"]["fresh"]
    return {
        "schema_version": "1.0",
        "collected_at": stamp(now),
        "provider": "NOAA Space Weather Prediction Center",
        "status": "VERIFIED" if scales_current else "UNVERIFIED",
        "status_definition": "VERIFIED means a freshly parsed NOAA current-scale record, not prediction accuracy",
        "current_scales": observed.get("scales"),
        "planetary_kp": observed.get("kp"),
        "latest_flare": observed.get("flare"),
        "bulletins": observed.get("bulletins"),
        "sources": sources,
        "agent_monitor": supervisor.public_report(),
    }


def write_snapshot(output=DEFAULT_OUTPUT, fetch=bounded_fetch, now=None):
    result = collect(fetch=fetch, now=now)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only NOAA space-weather snapshot collector")
    parser.add_argument("--watch", action="store_true",
                        help="refresh every five minutes while this process remains running")
    parser.add_argument("--interval", type=int, default=300,
                        help="watch polling interval in seconds; at least 300")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-blocked", action="store_true",
                        help="publish explicitly blocked sources without failing the static-site build")
    args = parser.parse_args(argv)
    if args.interval < 300:
        parser.error("minimum watch interval is 300 seconds")
    try:
        while True:
            result = write_snapshot(args.output)
            available = sum(s["status"] == "VERIFIED" for s in result["sources"])
            print(json.dumps({"at": result["collected_at"], "current_scales":
                              result["status"], "fresh_sources": available}, sort_keys=True), flush=True)
            if not args.watch:
                return 0 if available or args.allow_blocked else 2
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
