"""Credential-free NIFC WFIGS wildfire incident adapter.

WFIGS incident records are operational reports, not satellite heat detections.
Their presence does not by itself establish current fire behavior or danger at a
specific location.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"data"/"public"/"fire-incidents.json"
HOST="services3.arcgis.com"
LAYER="https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query"
FIELDS=("OBJECTID,IncidentName,IncidentTypeCategory,IncidentSize,DiscoveryAcres,"
        "FireDiscoveryDateTime,InitialResponseDateTime,ModifiedOnDateTime_dt,"
        "PercentContained,POOCity,POOCounty,POOState,IrwinID,UniqueFireIdentifier,"
        "ActiveFireCandidate,FireCause,IncidentShortDescription")
MAX_BYTES=2_000_000
MAX_FEATURES=500
FRESHNESS=timedelta(hours=72)

class FireSourceError(ValueError): pass

def query_url():
    return LAYER+"?"+urlencode({"f":"geojson","where":"IncidentTypeCategory='WF'","outFields":FIELDS,
        "returnGeometry":"true","outSR":"4326","resultRecordCount":str(MAX_FEATURES),
        "orderByFields":"ModifiedOnDateTime_dt DESC"})

def fetch(url):
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname!=HOST or not url.startswith(LAYER+"?"):
        raise FireSourceError("source outside WFIGS allowlist")
    request=Request(url,headers={"Accept":"application/geo+json,application/json","User-Agent":"SkyNet-918-FireWatch/1.0"})
    with urlopen(request,timeout=20) as response:
        final=urlsplit(response.geturl())
        if final.scheme!="https" or final.hostname!=HOST: raise FireSourceError("redirect outside WFIGS allowlist")
        raw=response.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES: raise FireSourceError("empty or oversized WFIGS response")
    return raw

def _number(value,label,minimum=None,maximum=None):
    try: result=float(value)
    except (TypeError,ValueError) as exc: raise FireSourceError("invalid "+label) from exc
    if not math.isfinite(result) or minimum is not None and result<minimum or maximum is not None and result>maximum:
        raise FireSourceError(label+" outside valid range")
    return result

def _date(value):
    if value in (None,""): return None
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        try: dt=datetime.fromtimestamp(value/1000,timezone.utc)
        except (ValueError,OSError,OverflowError) as exc: raise FireSourceError("invalid WFIGS date") from exc
    elif isinstance(value,str):
        try: dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        except ValueError as exc: raise FireSourceError("invalid WFIGS date") from exc
        if dt.tzinfo is None: raise FireSourceError("WFIGS date missing timezone")
    else: raise FireSourceError("invalid WFIGS date type")
    return dt.astimezone(timezone.utc)

def _stamp(value): return value.isoformat(timespec="seconds").replace("+00:00","Z") if value else None

def normalize(raw,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try: payload=json.loads(raw)
    except (UnicodeError,json.JSONDecodeError) as exc: raise FireSourceError("invalid WFIGS JSON") from exc
    if payload.get("type")!="FeatureCollection" or not isinstance(payload.get("features"),list):
        raise FireSourceError("WFIGS schema mismatch")
    if len(payload["features"])>MAX_FEATURES: raise FireSourceError("too many WFIGS features")
    incidents=[]
    for feature in payload["features"]:
        if feature.get("type")!="Feature" or not isinstance(feature.get("properties"),dict): raise FireSourceError("malformed WFIGS feature")
        p=feature["properties"]; geometry=feature.get("geometry",{}); coords=geometry.get("coordinates",[])
        if p.get("IncidentTypeCategory")!="WF": raise FireSourceError("non-wildfire record in filtered response")
        if geometry.get("type")!="Point" or len(coords)<2: raise FireSourceError("wildfire location missing")
        lon=_number(coords[0],"longitude",-180,180); lat=_number(coords[1],"latitude",-90,90)
        modified=_date(p.get("ModifiedOnDateTime_dt")); discovered=_date(p.get("FireDiscoveryDateTime"))
        if modified and modified>now+timedelta(minutes=10): raise FireSourceError("future-dated WFIGS update")
        identifier=str(p.get("IrwinID") or p.get("UniqueFireIdentifier") or p.get("OBJECTID") or "")
        if not identifier or len(identifier)>100: raise FireSourceError("wildfire identifier missing")
        size=None if p.get("IncidentSize") is None else _number(p["IncidentSize"],"incident size",0)
        contained=None if p.get("PercentContained") is None else _number(p["PercentContained"],"containment",0,100)
        incidents.append({"id":"nifc:"+identifier.strip("{}"),"incident_name":str(p.get("IncidentName") or "Unnamed wildfire")[:100],
            "incident_type":"wildfire","reported_acres":size,"percent_contained":contained,"discovered_at":_stamp(discovered),
            "modified_at":_stamp(modified),"fresh":bool(modified and -timedelta(minutes=10)<=now-modified<=FRESHNESS),
            "active_fire_candidate":p.get("ActiveFireCandidate") is True,"location":{"city":str(p.get("POOCity") or "")[:80],
            "county":str(p.get("POOCounty") or "")[:80],"state":str(p.get("POOState") or "")[:20]},
            "geometry":{"type":"Point","coordinates":[lon,lat]},"description":str(p.get("IncidentShortDescription") or "")[:240],
            "source":"NIFC WFIGS","source_url":LAYER.rsplit("/query",1)[0],"evidence_status":"OBSERVED_EVENT",
            "interpretation":"Operational incident record; not a satellite thermal anomaly or automatic danger determination"})
    return incidents

def collect(fetcher=fetch,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); url=query_url()
    try:
        raw=fetcher(url); incidents=normalize(raw,now)
        status={"source":"NIFC WFIGS current wildfire incidents","status":"VERIFIED","checked_at":_stamp(now),
            "source_url":LAYER.rsplit("/query",1)[0],"detail":f"{len(incidents)} schema-validated operational wildfire incident record(s)",
            "sha256":hashlib.sha256(raw).hexdigest()}
    except (FireSourceError,OSError,TimeoutError) as exc:
        incidents=[]; status={"source":"NIFC WFIGS current wildfire incidents","status":"BLOCKED","checked_at":_stamp(now),
            "source_url":LAYER.rsplit("/query",1)[0],"detail":type(exc).__name__+": "+str(exc)[:150]}
    return {"schema_version":"1.0","collected_at":_stamp(now),"provider":"National Interagency Fire Center WFIGS",
        "incidents":incidents,"source_status":status,"satellite_thermal_anomalies":None,
        "interpretation":"WFIGS records replace credential-gated FIRMS for reported U.S. incidents; no satellite detection is implied."}

def write_snapshot(path=OUTPUT,fetcher=fetch,now=None):
    result=collect(fetcher,now); path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); temp.replace(path); return result

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=OUTPUT); parser.add_argument("--allow-blocked",action="store_true"); args=parser.parse_args(argv)
    result=write_snapshot(args.output); print(json.dumps({"status":result["source_status"]["status"],"incidents":len(result["incidents"])}))
    return 0 if result["source_status"]["status"]=="VERIFIED" or args.allow_blocked else 2
if __name__=="__main__": raise SystemExit(main())
