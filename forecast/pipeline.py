"""Deterministic, stdlib-only feed normalization for reproducible local/CI runs."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE = {"OFFICIAL_FORECAST", "OFFICIAL_WARNING", "OBSERVED_EVENT", "MODEL_RISK", "EXPERIMENTAL_ANOMALY", "SIMULATED"}
MAX_BYTES = 5_000_000

class ValidationError(ValueError): pass

def iso(value):
    if not isinstance(value, str): raise ValidationError("timestamp must be a string")
    try: dt=datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e: raise ValidationError("invalid timestamp") from e
    if dt.tzinfo is None: raise ValidationError("timestamp must include timezone")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def load_json(path):
    path=Path(path)
    if path.stat().st_size > MAX_BYTES: raise ValidationError("payload too large")
    return json.loads(path.read_text(encoding="utf-8"))

def usgs(payload):
    if payload.get("type") != "FeatureCollection": raise ValidationError("USGS schema mismatch")
    out=[]
    for f in payload.get("features", []):
        p=f.get("properties", {}); g=f.get("geometry", {}); coords=g.get("coordinates", [])
        if len(coords)<3 or not isinstance(p.get("time"),(int,float)): raise ValidationError("malformed USGS event")
        at=datetime.fromtimestamp(p["time"]/1000, timezone.utc).isoformat().replace("+00:00","Z")
        out.append({"id":"usgs:"+str(f.get("id")),"hazard":"earthquake","source":"USGS","source_url":p.get("url"),"summary":p.get("title"),"detail":f"Magnitude {p.get('mag')} · depth {coords[2]} km","valid_at":at,"evidence_status":"OBSERVED_EVENT","geometry":{"type":"Point","coordinates":coords[:2]},"magnitude":p.get("mag"),"depth_km":coords[2],"schema_version":"1.0"})
    return out

def nws(payload):
    if payload.get("type") != "FeatureCollection": raise ValidationError("NWS schema mismatch")
    out=[]
    for f in payload.get("features",[]):
        p=f.get("properties",{}); issued=iso(p.get("sent")); expires=iso(p.get("expires"))
        if expires <= issued: raise ValidationError("warning expires before issue")
        out.append({"id":"nws:"+str(p.get("id") or f.get("id")),"hazard":"storm","source":"NOAA/NWS","source_url":p.get("@id"),"summary":p.get("headline") or p.get("event"),"detail":p.get("description","")[:1000],"valid_at":issued,"expires":expires,"evidence_status":"OFFICIAL_WARNING","severity":p.get("severity","Unknown"),"area":p.get("areaDesc","Unknown"),"geometry":f.get("geometry"),"schema_version":"1.0"})
    return out

def provenance(raw): return hashlib.sha256(raw).hexdigest()

def fuse(events):
    """Conservative deterministic grouping; never assigns probabilistic confidence."""
    return [{**e,"fusion":{"reliability":"official" if e["source"] in {"USGS","NOAA/NWS"} else "unknown","corroborated":False,"rule_version":"1.0"}} for e in events]
