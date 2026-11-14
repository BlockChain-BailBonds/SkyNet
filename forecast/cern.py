"""SkyNet CERN public-research connector.

Only catalog metadata and public CERN pages are retrieved. No accelerator
control, raw detector stream, environmental sensor access, or prediction.
All URLs are compiled-in; redirects remain on the original HTTPS host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "cern-status.json"
API = "https://opendata.cern.ch/api/records/"
CLOUD = "https://home.cern/science/experiments/cloud/"
VISTAR = "https://vistar-capture.s3.cern.ch/index.html"
MAX_BYTES = 800_000
TIMEOUT = 9
MAX_RECORDS = 4
AGENTS = (
    ("CERN.CMS", "CMS", "catalog", API + "?" + urlencode({"experiment": "CMS", "type": "Dataset", "size": MAX_RECORDS})),
    ("CERN.ATLAS", "ATLAS", "catalog", API + "?" + urlencode({"experiment": "ATLAS", "type": "Dataset", "size": MAX_RECORDS})),
    ("CERN.ALICE", "ALICE", "catalog", API + "?" + urlencode({"experiment": "ALICE", "type": "Dataset", "size": MAX_RECORDS})),
    ("CERN.LHCB", "LHCb", "catalog", API + "?" + urlencode({"experiment": "LHCb", "type": "Dataset", "size": MAX_RECORDS})),
    ("CERN.CLOUD", "CLOUD atmospheric experiment", "research_page", CLOUD),
    ("CERN.LHC_VISTAR", "LHC public display directory", "display_directory", VISTAR),
)
ID_PATTERN = re.compile(r"^[0-9]{1,20}$")


class SourceRejected(ValueError):
    """Source response cannot be counted as a validated public observation."""


def stamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("now must contain a timezone")
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if new.scheme != "https" or new.hostname != original.hostname:
            raise SourceRejected("REDIRECT_REJECTED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url: str) -> bytes:
    allowed = {agent[3] for agent in AGENTS}
    if url not in allowed:
        raise SourceRejected("POLICY_REJECTED")
    opener = build_opener(SameHostRedirect())
    request = Request(url, headers={
        "Accept": "application/json, text/html;q=0.8",
        "User-Agent": "SkyNet-CERN-Public-Research/1.0",
    })
    with opener.open(request, timeout=TIMEOUT) as response:
        final = urlsplit(response.geturl())
        initial = urlsplit(url)
        if final.scheme != "https" or final.hostname != initial.hostname:
            raise SourceRejected("REDIRECT_REJECTED")
        content_type = response.headers.get_content_type()
        expected = "application/json" if initial.hostname == "opendata.cern.ch" else "text/html"
        if content_type != expected:
            raise SourceRejected("CONTENT_TYPE_REJECTED")
        raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise SourceRejected("PAYLOAD_REJECTED")
        return raw


def _title(value):
    if isinstance(value, str):
        return value.strip()[:180]
    if isinstance(value, list) and value:
        item = value[0]
        if isinstance(item, dict):
            return _title(item.get("title", ""))
    return ""


def normalize_catalog(raw: bytes) -> dict:
    try:
        obj = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise SourceRejected("SCHEMA_REJECTED") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("hits"), dict):
        raise SourceRejected("SCHEMA_REJECTED")
    hits = obj["hits"].get("hits")
    if not isinstance(hits, list) or len(hits) > MAX_RECORDS:
        raise SourceRejected("SCHEMA_REJECTED")
    total = obj["hits"].get("total")
    if isinstance(total, dict):
        total = total.get("value")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise SourceRejected("SCHEMA_REJECTED")
    records = []
    for item in hits:
        if not isinstance(item, dict):
            raise SourceRejected("SCHEMA_REJECTED")
        recid = item.get("id", item.get("recid"))
        if isinstance(recid, int) and not isinstance(recid, bool):
            recid = str(recid)
        if not isinstance(recid, str) or not ID_PATTERN.fullmatch(recid):
            raise SourceRejected("SCHEMA_REJECTED")
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise SourceRejected("SCHEMA_REJECTED")
        title = _title(metadata.get("title", metadata.get("titles", "")))
        records.append({
            "record_id": recid,
            "title": title or "Untitled public record",
            "url": "https://opendata.cern.ch/record/" + recid,
        })
    return {"matched_records": total, "sampled_records": records}


def normalize_page(raw: bytes) -> dict:
    try:
        start = raw[:4096].decode("utf-8", errors="strict").lower()
    except UnicodeError as exc:
        raise SourceRejected("SCHEMA_REJECTED") from exc
    if "<html" not in start and "<!doctype html" not in start:
        raise SourceRejected("SCHEMA_REJECTED")
    return {"bytes_inspected": len(raw), "numeric_samples": 0}


def collect_one(spec: tuple, at: str, fetcher=fetch_bytes) -> dict:
    agent_id, label, kind, url = spec
    out = {
        "id": agent_id, "name": label, "kind": kind, "source_url": url,
        "checked_at": at, "status": "BLOCKED",
        "measurement_status": "UNVERIFIED",
        "live_sensor_access": False, "trainable_numeric_samples": 0,
        "reason": "NOT_COLLECTED", "response_sha256": None,
    }
    try:
        raw = fetcher(url)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
            raise SourceRejected("PAYLOAD_REJECTED")
        details = normalize_catalog(raw) if kind == "catalog" else normalize_page(raw)
    except (SourceRejected, ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, SourceRejected):
            out["reason"] = str(exc) if str(exc) in {
                "REDIRECT_REJECTED", "POLICY_REJECTED", "CONTENT_TYPE_REJECTED",
                "PAYLOAD_REJECTED", "SCHEMA_REJECTED"} else "SCHEMA_REJECTED"
        else:
            out["reason"] = "FETCH_FAILED"
        return out
    out.update({
        "status": "VERIFIED", "reason": "PUBLIC_METADATA_RETRIEVED",
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "response_bytes": len(raw), "metadata": details,
    })
    return out


def make_report(at: str, fetcher=fetch_bytes) -> dict:
    """Independent agents with bounded concurrent public requests."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        agents = list(pool.map(lambda spec: collect_one(spec, at, fetcher), AGENTS))
    chain = "0" * 64
    evidence = []
    for agent in agents:
        event = {
            "agent_id": agent["id"], "checked_at": at, "status": agent["status"],
            "response_sha256": agent["response_sha256"],
            "reason": agent["reason"], "prev_hash": chain,
        }
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        event["chain_hash"] = hashlib.sha256(encoded).hexdigest()
        chain = event["chain_hash"]
        evidence.append(event)
    return {
        "schema_version": "1.0", "collected_at": at,
        "sources_checked": len(agents),
        "metadata_retrievals_verified": sum(x["status"] == "VERIFIED" for x in agents),
        "live_detector_streams": 0, "direct_cern_sensor_access": False,
        "numeric_physics_observations": 0, "correlation_status": "BLOCKED",
        "correlation_reason": "NO_COMPARABLE_TIMESERIES",
        "learning_policy": "METADATA_ONLY_NO_TRAINING",
        "agents": agents, "evidence": evidence, "chain_head": chain,
        "interpretation": "VERIFIED means HTTP payload schema checked, not live beam or physical measurement",
    }


def save(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, bounded CERN public metadata collection")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--allow-blocked", action="store_true",
                        help="Publish explicit blocked states without failing the Pages build")
    args = parser.parse_args(argv)
    report = make_report(stamp(datetime.now(timezone.utc)))
    save(report, args.output)
    print(json.dumps({"collected_at": report["collected_at"],
                      "verified_metadata_sources": report["metadata_retrievals_verified"],
                      "blocked_sources": report["sources_checked"] - report["metadata_retrievals_verified"]}))
    return 0 if args.allow_blocked or report["metadata_retrievals_verified"] == report["sources_checked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
